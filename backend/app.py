import json
import os
import secrets
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

SESSIONS: dict[str, User] = {}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _json_bytes(payload: dict | list) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


class SecureChatHandler(BaseHTTPRequestHandler):
    server_version = "SecureCampusChatbot/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, payload: dict | list, status: int = HTTPStatus.OK) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, filename: str | None = None) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
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
        return SESSIONS.get(token)

    def _require_user(self) -> User | None:
        user = self._current_user()
        if user is None:
            self._send_json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

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

        if parsed.path == "/api/login":
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            user = authenticate(str(payload.get("username", "")), str(payload.get("password", "")))
            if user is None:
                self._send_json({"error": "Invalid username or password"}, HTTPStatus.UNAUTHORIZED)
                return
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = user
            self._send_json({"token": token, "user": public_profile(user)})
            return

        if parsed.path == "/api/logout":
            token = self._session_token()
            if token:
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
    httpd.serve_forever()


if __name__ == "__main__":
    main()
