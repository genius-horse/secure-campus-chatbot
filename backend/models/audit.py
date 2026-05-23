from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    username = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False, index=True)
    action = Column(String(32), nullable=False, index=True)
    risk = Column(String(16), nullable=False, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    policy_hits = Column(JSON, default=list)
    citations = Column(JSON, default=list)
    generation_mode = Column(String(32))
    client_ip = Column(String(64))
