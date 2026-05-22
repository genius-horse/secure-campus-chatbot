
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from chatbot import respond
from config import load_env_file
from database import audit_metrics, audit_summary, export_audit_csv, init_db, list_audit_logs
from evaluation import run_security_evaluation
from llm_provider import provider_status
from retrieval import (
    add_knowledge,
    delete_knowledge,
    load_knowledge,
    update_knowledge,
    visible_knowledge,
)
from users import User, authenticate, public_profile


load_env_file()

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8010"))
MAX_MESSAGE_LENGTH = 5000
SESSION_TTL_SECONDS = 1800
MAX_LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 60

SESSIONS: dict[str, tuple[User, float]] = {}
CONVERSATIONS: dict[str, list[dict]] = {}
MAX_HISTORY_LENGTH = 20
_login_attempts: list[float] = []
_rate_lock = threading.Lock()
_session_lock = threading.Lock()
_conv_lock = threading.Lock()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def _json_bytes(payload: dict | list) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _cleanup_sessions(now: float | None = None) -> int:
    now = now or time.monotonic()
    with _session_lock:
        expired = [t for t, (_, ts) in SESSIONS.items() if now - ts > SESSION_TTL_SECONDS]
        for t in expired:
            SESSIONS.pop(t, None)
    with _conv_lock:
        for t in expired:
            CONVERSATIONS.pop(t, None)
    return len(expired)


def _check_rate_limit() -> bool:
    with _rate_lock:
        now = time.monotonic()
        cutoff = now - LOGIN_WINDOW_SECONDS
        _login_attempts[:] = [t for t in _login_attempts if t > cutoff]
        return len(_login_attempts) < MAX_LOGIN_ATTEMPTS


def _record_login_attempt() -> None:
    with _rate_lock:
        _login_attempts.append(time.monotonic())


class SecureChatHandler(BaseHTTPRequestHandler):
    server_version = "SecureCampusChatbot/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def _send_json(self, payload: dict | list, status: int = HTTPStatus.OK) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)
            return
        suffix = path.suffix.lower()
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # Short cache for development, long cache for production
        if os.environ.get("APP_ENV") == "development":
            self.send_header("Cache-Control", "no-cache")
        elif suffix in {".html", ".css", ".js"}:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "public, max-age=86400")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, filename: str | None = None) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > 64 * 1024:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _session_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth.removeprefix("Bearer ").strip()
        return None

    def _current_user(self) -> User | None:
        token = self._session_token()
        if not token:
            return None
        with _session_lock:
            entry = SESSIONS.get(token)
            if entry is None:
                return None
            user, last_active = entry
            now = time.monotonic()
            if now - last_active > SESSION_TTL_SECONDS:
                SESSIONS.pop(token, None)
                return None
            SESSIONS[token] = (user, now)
            return user

    def _require_user(self) -> User | None:
        user = self._current_user()
        if user is None:
            self._send_json({"error": "需要身份认证"}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        _cleanup_sessions()

        if path == "/api/me":
            user = self._require_user()
            if user:
                self._send_json({"user": public_profile(user)})
            return

        if path == "/api/config":
            self._send_json(provider_status())
            return

        if path == "/api/knowledge":
            user = self._require_user()
            if user:
                self._send_json({"items": visible_knowledge(user.role)})
            return

        if path == "/api/audit":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["100"])[0])
            filters = {}
            for key in ("risk", "action", "role", "username", "search", "date_from", "date_to"):
                val = query.get(key, [None])[0]
                if val:
                    filters[key] = val
            self._send_json({
                "summary": audit_summary(),
                "logs": list_audit_logs(limit=limit, **filters),
            })
            return

        if path == "/api/audit/metrics":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
            self._send_json(audit_metrics())
            return

        if path == "/api/audit/export":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["500"])[0])
            self._send_text(
                export_audit_csv(limit=limit),
                "text/csv; charset=utf-8",
                filename="secure-campus-audit.csv",
            )
            return

        if path == "/":
            self._send_file(FRONTEND_DIR / "index.html")
            return

        requested = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if FRONTEND_DIR.resolve() not in requested.parents and requested != FRONTEND_DIR.resolve():
            self._send_json({"error": "无效路径"}, HTTPStatus.BAD_REQUEST)
            return
        self._send_file(requested)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        _cleanup_sessions()

        if parsed.path == "/api/login":
            if not _check_rate_limit():
                self._send_json(
                    {"error": "登录尝试次数过多，请稍后再试。"},
                    HTTPStatus.TOO_MANY_REQUESTS,
                )
                return
            _record_login_attempt()
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "无效的JSON格式"}, HTTPStatus.BAD_REQUEST)
                return
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            if len(username) > 64 or len(password) > 128:
                self._send_json({"error": "用户名或密码错误"}, HTTPStatus.UNAUTHORIZED)
                return
            user = authenticate(username, password)
            if user is None:
                self._send_json({"error": "用户名或密码错误"}, HTTPStatus.UNAUTHORIZED)
                return
            token = secrets.token_urlsafe(32)
            with _session_lock:
                SESSIONS[token] = (user, time.monotonic())
            self._send_json({"token": token, "user": public_profile(user)})
            return

        if parsed.path == "/api/logout":
            token = self._session_token()
            if token:
                with _session_lock:
                    SESSIONS.pop(token, None)
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/chat":
            user = self._require_user()
            if not user:
                return
            token = self._session_token()
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "无效的JSON格式"}, HTTPStatus.BAD_REQUEST)
                return
            message = str(payload.get("message", ""))
            clear_history = bool(payload.get("clear_history", False))

            # Handle pure clear-history request (no message)
            if clear_history and not message.strip():
                with _conv_lock:
                    CONVERSATIONS.pop(token, None)
                self._send_json({
                    "action": "allowed",
                    "risk": "none",
                    "answer": "",
                    "policy_hits": [],
                    "citations": [],
                    "audit_id": None,
                    "generation_mode": "local",
                    "llm_error": None,
                    "history_message_count": 0,
                    "history_cleared": True,
                })
                return

            if len(message) > MAX_MESSAGE_LENGTH:
                self._send_json(
                    {"error": f"消息过长，最大允许{MAX_MESSAGE_LENGTH}个字符。"},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            # Manage conversation history
            with _conv_lock:
                if clear_history and token:
                    CONVERSATIONS.pop(token, None)
                history = CONVERSATIONS.get(token, []) if token else []

            result = respond(user, message, history if history else None)

            # Store exchange in history
            if token and result.get("action") != "blocked":
                with _conv_lock:
                    conv = CONVERSATIONS.setdefault(token, [])
                    conv.append({"role": "user", "content": message})
                    conv.append({"role": "assistant", "content": result["answer"]})
                    if len(conv) > MAX_HISTORY_LENGTH * 2:
                        CONVERSATIONS[token] = conv[-(MAX_HISTORY_LENGTH * 2):]

            self._send_json(result)
            return

        if parsed.path == "/api/security-tests":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
            self._send_json(run_security_evaluation())
            return

        if parsed.path == "/api/knowledge/manage":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "需要管理员权限"}, HTTPStatus.FORBIDDEN)
                return
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "无效的JSON格式"}, HTTPStatus.BAD_REQUEST)
                return

            action = str(payload.get("action", "list")).strip().lower()

            if action == "list":
                docs = load_knowledge()
                self._send_json({
                    "items": [
                        {
                            "id": d.id,
                            "title": d.title,
                            "min_role": d.min_role,
                            "sensitivity": d.sensitivity,
                            "keywords": d.keywords,
                            "content": d.content,
                        }
                        for d in docs
                    ]
                })
                return

            if action == "add":
                try:
                    doc = add_knowledge(
                        id=str(payload["id"]).strip(),
                        title=str(payload["title"]).strip(),
                        min_role=str(payload["min_role"]).strip(),
                        sensitivity=str(payload["sensitivity"]).strip(),
                        keywords=list(payload.get("keywords", [])),
                        content=str(payload["content"]).strip(),
                    )
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
                    return
                except KeyError as exc:
                    self._send_json({"error": f"缺少字段：{exc}"}, HTTPStatus.BAD_REQUEST)
                    return
                self._send_json({
                    "ok": True,
                    "item": {
                        "id": doc.id,
                        "title": doc.title,
                        "min_role": doc.min_role,
                        "sensitivity": doc.sensitivity,
                        "keywords": doc.keywords,
                        "content": doc.content,
                    }
                })
                return

            if action == "update":
                kb_id = str(payload.get("id", "")).strip()
                if not kb_id:
                    self._send_json({"error": "缺少id字段"}, HTTPStatus.BAD_REQUEST)
                    return
                updates = {}
                for field in ("title", "min_role", "sensitivity", "content"):
                    if field in payload:
                        updates[field] = str(payload[field]).strip()
                if "keywords" in payload:
                    updates["keywords"] = list(payload["keywords"])
                try:
                    doc = update_knowledge(kb_id, **updates)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({
                    "ok": True,
                    "item": {
                        "id": doc.id,
                        "title": doc.title,
                        "min_role": doc.min_role,
                        "sensitivity": doc.sensitivity,
                        "keywords": doc.keywords,
                        "content": doc.content,
                    }
                })
                return

            if action == "delete":
                kb_id = str(payload.get("id", "")).strip()
                if not kb_id:
                    self._send_json({"error": "缺少id字段"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    delete_knowledge(kb_id)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"ok": True})
                return

            self._send_json({"error": f"不支持的操作：{action}"}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"error": "未找到"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), SecureChatHandler)
    print(f"安全校园助手运行于 http://{HOST}:{PORT}")
    print("演示账户：alice/student123, prof/teacher123, admin/admin123")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        httpd.server_close()


if __name__ == "__main__":
    main()
