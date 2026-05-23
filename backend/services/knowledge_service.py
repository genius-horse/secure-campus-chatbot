from typing import Optional

from sqlalchemy.orm import Session

from models.knowledge import KnowledgeDoc
from services.retrieval_service import compute_doc_embedding


def list_all(db: Session) -> list[KnowledgeDoc]:
    return db.query(KnowledgeDoc).all()


def get_by_id(db: Session, doc_id: str) -> Optional[KnowledgeDoc]:
    return db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()


def create(
    db: Session,
    *,
    doc_id: str,
    title: str,
    min_role: str,
    sensitivity: str,
    keywords: list[str],
    content: str,
) -> KnowledgeDoc:
    existing = get_by_id(db, doc_id)
    if existing:
        raise ValueError(f"知识条目 '{doc_id}' 已存在")

    doc = KnowledgeDoc(
        id=doc_id,
        title=title,
        min_role=min_role,
        sensitivity=sensitivity,
        keywords=keywords,
        content=content,
    )
    doc.embedding = compute_doc_embedding(doc)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def update(
    db: Session,
    doc_id: str,
    **kwargs,
) -> KnowledgeDoc:
    doc = get_by_id(db, doc_id)
    if doc is None:
        raise ValueError(f"知识条目 '{doc_id}' 不存在")

    for key, value in kwargs.items():
        if value is not None and hasattr(doc, key):
            setattr(doc, key, value)

    # 如果内容或标题变更，重新计算 embedding
    if any(k in kwargs for k in ("title", "content", "keywords")):
        doc.embedding = compute_doc_embedding(doc)

    db.commit()
    db.refresh(doc)
    return doc


def delete(db: Session, doc_id: str) -> None:
    doc = get_by_id(db, doc_id)
    if doc is None:
        raise ValueError(f"知识条目 '{doc_id}' 不存在")
    db.delete(doc)
    db.commit()
