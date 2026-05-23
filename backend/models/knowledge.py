from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, JSON

from models.base import Base


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(String(64), primary_key=True)
    title = Column(String(256), nullable=False)
    min_role = Column(String(16), nullable=False, default="public")
    sensitivity = Column(String(16), nullable=False, default="public")
    keywords = Column(JSON, default=list)
    content = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
