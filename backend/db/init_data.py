import json
import hashlib
import hmac
from pathlib import Path

from sqlalchemy.orm import Session

from db.session import engine
from models.base import Base
from models.user import User
from models.knowledge import KnowledgeDoc


ROOT_DIR = Path(__file__).resolve().parents[2]
KB_PATH = ROOT_DIR / "data" / "campus_kb.json"

_DEMO_ACCOUNTS = {
    "alice": {
        "display_name": "陈爱丽",
        "role": "student",
        "salt": "course-demo-student",
        "password": "student123",
    },
    "prof": {
        "display_name": "王教授",
        "role": "teacher",
        "salt": "course-demo-teacher",
        "password": "teacher123",
    },
    "admin": {
        "display_name": "安全管理员",
        "role": "admin",
        "salt": "course-demo-admin",
        "password": "admin123",
    },
}


def _derive_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def init_users(db: Session) -> None:
    for username, info in _DEMO_ACCOUNTS.items():
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            continue
        user = User(
            username=username,
            display_name=info["display_name"],
            role=info["role"],
            salt=info["salt"],
            password_hash=_derive_password(info["password"], info["salt"]),
        )
        db.add(user)
    db.commit()


def init_knowledge(db: Session) -> None:
    if not KB_PATH.exists():
        return

    raw_docs = json.loads(KB_PATH.read_text(encoding="utf-8"))
    for item in raw_docs:
        existing = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == item["id"]).first()
        if existing:
            changed = False
            for field in ("title", "min_role", "sensitivity", "content"):
                new_value = item.get(field, "public" if field in {"min_role", "sensitivity"} else "")
                if getattr(existing, field) != new_value:
                    setattr(existing, field, new_value)
                    changed = True
            new_keywords = item.get("keywords", [])
            if existing.keywords != new_keywords:
                existing.keywords = new_keywords
                changed = True
            if changed:
                existing.embedding = None
            continue
        doc = KnowledgeDoc(
            id=item["id"],
            title=item["title"],
            min_role=item.get("min_role", "public"),
            sensitivity=item.get("sensitivity", "public"),
            keywords=item.get("keywords", []),
            content=item["content"],
            embedding=None,
        )
        db.add(doc)
    db.commit()


def compute_missing_embeddings(db: Session) -> int:
    """为没有 embedding 的知识条目计算向量。返回计算数量。"""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return 0

    docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.embedding.is_(None)).all()
    if not docs:
        return 0

    model = SentenceTransformer("all-MiniLM-L6-v2")
    count = 0
    for doc in docs:
        text = f"{doc.title} {' '.join(doc.keywords or [])} {doc.content}"
        embedding = model.encode(text, normalize_embeddings=True)
        doc.embedding = embedding.tolist()
        count += 1
    db.commit()
    return count


def init_database(db: Session) -> None:
    Base.metadata.create_all(bind=engine)
    init_users(db)
    init_knowledge(db)
    compute_missing_embeddings(db)
