from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default="student")
    password_hash = Column(String(256), nullable=False)
    salt = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
