import json
import sqlite3
from collections import Counter
from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from threading import Lock


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "data" / "audit.sqlite3"

_LOCK = Lock()


def init_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                risk TEXT NOT NULL,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                policy_hits TEXT NOT NULL,
                citations TEXT NOT NULL
            )
            """
        )
        conn.commit()


def append_audit_log(
    *,
    username: str,
    role: str,
    action: str,
    risk: str,
    message: str,
    response: str,
    policy_hits: list[dict],
    citations: list[dict],
    path: Path = DB_PATH,
) -> int:
    init_db(path)
    created_at = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        with sqlite3.connect(path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log (
                    created_at, username, role, action, risk, message,
                    response, policy_hits, citations
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    username,
                    role,
                    action,
                    risk,
                    message,
                    response,
                    json.dumps(policy_hits, ensure_ascii=False),
                    json.dumps(citations, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)


def list_audit_logs(limit: int = 100, path: Path = DB_PATH) -> list[dict]:
    init_db(path)
    safe_limit = max(1, min(int(limit), 500))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, username, role, action, risk, message,
                   response, policy_hits, citations
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    logs = []
    for row in rows:
        item = dict(row)
        item["policy_hits"] = json.loads(item["policy_hits"])
        item["citations"] = json.loads(item["citations"])
        logs.append(item)
    return logs


def audit_summary(path: Path = DB_PATH) -> dict:
    init_db(path)
    with sqlite3.connect(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        blocked = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'blocked'"
        ).fetchone()[0]
        high_risk = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE risk = 'high'"
        ).fetchone()[0]
    return {
        "total": total,
        "blocked": blocked,
        "high_risk": high_risk,
    }


def audit_metrics(path: Path = DB_PATH) -> dict:
    logs = list_audit_logs(limit=500, path=path)
    by_action = Counter(item["action"] for item in logs)
    by_risk = Counter(item["risk"] for item in logs)
    by_role = Counter(item["role"] for item in logs)
    policy_hits = Counter(
        hit.get("rule_id", "unknown")
        for item in logs
        for hit in item.get("policy_hits", [])
    )
    return {
        "summary": audit_summary(path),
        "by_action": dict(by_action),
        "by_risk": dict(by_risk),
        "by_role": dict(by_role),
        "top_policy_hits": dict(policy_hits.most_common(8)),
    }


def export_audit_csv(limit: int = 500, path: Path = DB_PATH) -> str:
    rows = list_audit_logs(limit=limit, path=path)
    output = StringIO()
    writer = DictWriter(
        output,
        fieldnames=[
            "id",
            "created_at",
            "username",
            "role",
            "action",
            "risk",
            "message",
            "policy_hits",
            "citations",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "username": row["username"],
                "role": row["role"],
                "action": row["action"],
                "risk": row["risk"],
                "message": row["message"],
                "policy_hits": json.dumps(row["policy_hits"], ensure_ascii=False),
                "citations": json.dumps(row["citations"], ensure_ascii=False),
            }
        )
    return output.getvalue()
