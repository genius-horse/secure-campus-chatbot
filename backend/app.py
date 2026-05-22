
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
from retrieval import visible_knowledge
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
_login_attempts: list[float] = []
_rate_lock = threading.Lock()
_session_lock = threading.Lock()

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
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        suffix = path.suffix.lower()
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        if suffix in {".html", ".css", ".js"}:
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
            self._send_json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
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
                self._send_json({"error": "Admin role required"}, HTTPStatus.FORBIDDEN)
                return
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["100"])[0])
            self._send_json({"summary": audit_summary(), "logs": list_audit_logs(limit=limit)})
            return

        if path == "/api/audit/metrics":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "Admin role required"}, HTTPStatus.FORBIDDEN)
                return
            self._send_json(audit_metrics())
            return

        if path == "/api/audit/export":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "Admin role required"}, HTTPStatus.FORBIDDEN)
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
            self._send_json({"error": "Invalid path"}, HTTPStatus.BAD_REQUEST)
            return
        self._send_file(requested)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        _cleanup_sessions()

        if parsed.path == "/api/login":
            if not _check_rate_limit():
                self._send_json(
                    {"error": "Too many login attempts. Please wait and try again."},
                    HTTPStatus.TOO_MANY_REQUESTS,
                )
                return
            _record_login_attempt()
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            if len(username) > 64 or len(password) > 128:
                self._send_json({"error": "Invalid username or password"}, HTTPStatus.UNAUTHORIZED)
                return
            user = authenticate(username, password)
            if user is None:
                self._send_json({"error": "Invalid username or password"}, HTTPStatus.UNAUTHORIZED)
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
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            message = str(payload.get("message", ""))
            if len(message) > MAX_MESSAGE_LENGTH:
                self._send_json(
                    {"error": f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(respond(user, message))
            return

        if parsed.path == "/api/security-tests":
            user = self._require_user()
            if not user:
                return
            if user.role != "admin":
                self._send_json({"error": "Admin role required"}, HTTPStatus.FORBIDDEN)
                return
            self._send_json(run_security_evaluation())
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), SecureChatHandler)
    print(f"Secure Campus Assistant running at http://{HOST}:{PORT}")
    print("Demo accounts: alice/student123, prof/teacher123, admin/admin123")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()


if __name__ == "__main__":
    main()
