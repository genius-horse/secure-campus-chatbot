from pydantic import BaseModel
from typing import Optional


class AuditQuery(BaseModel):
    limit: int = 100
    risk: Optional[str] = None
    action: Optional[str] = None
    role: Optional[str] = None
    username: Optional[str] = None
    search: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
