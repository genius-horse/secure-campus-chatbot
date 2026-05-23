import json
from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.audit import AuditLog


def append_audit_log(
    db: Session,
    *,
    username: str,
    role: str,
    action: str,
    risk: str,
    message: str,
    response: str,
    policy_hits: list[dict],
    citations: list[dict],
    generation_mode: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> int:
    log = AuditLog(
        username=username,
        role=role,
        action=action,
        risk=risk,
        message=message,
        response=response,
        policy_hits=policy_hits,
        citations=citations,
        generation_mode=generation_mode,
        client_ip=client_ip,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log.id


def list_audit_logs(
    db: Session,
    limit: int = 100,
    risk: Optional[str] = None,
    action: Optional[str] = None,
    role: Optional[str] = None,
    username: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    safe_limit = max(1, min(limit, 500))
    query = db.query(AuditLog).order_by(AuditLog.id.desc())

    if risk:
        query = query.filter(AuditLog.risk == risk)
    if action:
        query = query.filter(AuditLog.action == action)
    if role:
        query = query.filter(AuditLog.role == role)
    if username:
        query = query.filter(AuditLog.username == username)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (AuditLog.message.like(like)) | (AuditLog.response.like(like))
        )
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to:
        query = query.filter(AuditLog.created_at <= date_to)

    rows = query.limit(safe_limit).all()

    logs = []
    for row in rows:
        logs.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "username": row.username,
                "role": row.role,
                "action": row.action,
                "risk": row.risk,
                "message": row.message,
                "response": row.response,
                "policy_hits": row.policy_hits or [],
                "citations": row.citations or [],
                "generation_mode": row.generation_mode,
            }
        )
    return logs


def audit_summary(db: Session) -> dict:
    total = db.query(func.count(AuditLog.id)).scalar() or 0
    blocked = (
        db.query(func.count(AuditLog.id)).filter(AuditLog.action == "blocked").scalar()
        or 0
    )
    high_risk = (
        db.query(func.count(AuditLog.id)).filter(AuditLog.risk == "high").scalar()
        or 0
    )
    return {
        "total": total,
        "blocked": blocked,
        "high_risk": high_risk,
    }


def audit_metrics(db: Session) -> dict:
    from collections import Counter

    logs = list_audit_logs(db, limit=500)
    by_action = Counter(item["action"] for item in logs)
    by_risk = Counter(item["risk"] for item in logs)
    by_role = Counter(item["role"] for item in logs)
    policy_hits = Counter(
        hit.get("rule_id", "unknown")
        for item in logs
        for hit in item.get("policy_hits", [])
    )
    return {
        "summary": audit_summary(db),
        "by_action": dict(by_action),
        "by_risk": dict(by_risk),
        "by_role": dict(by_role),
        "top_policy_hits": dict(policy_hits.most_common(8)),
    }


def export_audit_csv(db: Session, limit: int = 500) -> str:
    rows = list_audit_logs(db, limit=limit)
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
