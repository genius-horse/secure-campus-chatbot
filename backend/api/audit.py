from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_admin
from services import audit_service

router = APIRouter()


@router.get("/audit")
def list_logs(
    limit: int = Query(100, ge=1, le=500),
    risk: str | None = None,
    action: str | None = None,
    role: str | None = None,
    username: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    logs = audit_service.list_audit_logs(
        db,
        limit=limit,
        risk=risk,
        action=action,
        role=role,
        username=username,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "summary": audit_service.audit_summary(db),
        "logs": logs,
    }


@router.get("/audit/metrics")
def metrics(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return audit_service.audit_metrics(db)


@router.get("/audit/export")
def export(
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    csv = audit_service.export_audit_csv(db, limit=limit)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        csv,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="secure-campus-audit.csv"'},
    )
