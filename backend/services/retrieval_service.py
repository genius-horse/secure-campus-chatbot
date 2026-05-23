import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from core.constants import ROLE_ORDER
from models.knowledge import KnowledgeDoc


@dataclass(frozen=True)
class RetrievalHit:
    doc: KnowledgeDoc
    score: float
    allowed: bool


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese_terms = set(re.findall(r"[一-鿿]{2,}", lowered))
    return words | chinese_terms


def _keyword_score(query: str, doc: KnowledgeDoc) -> float:
    q_tokens = _tokenize(query)
    searchable = f"{doc.title} {' '.join(doc.keywords or [])} {doc.content}".lower()
    doc_tokens = _tokenize(searchable)

    score = len(q_tokens & doc_tokens)
    for keyword in doc.keywords or []:
        if keyword.lower() in query.lower():
            score += 4
    if any(part in searchable for part in q_tokens):
        score += 1
    return float(score)


_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        return _embedding_model
    except Exception:
        return None


def _compute_embedding(text: str) -> list[float] | None:
    model = _get_embedding_model()
    if model is None:
        return None
    emb = model.encode(text, normalize_embeddings=True)
    return emb.tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    return float(np.dot(np.array(a), np.array(b)))


def compute_doc_embedding(doc: KnowledgeDoc) -> list[float] | None:
    text = f"{doc.title} {' '.join(doc.keywords or [])} {doc.content}"
    return _compute_embedding(text)


def hybrid_search(
    db: Session,
    query: str,
    user_role: str,
    top_k: int = 5,
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
    min_score: float = 0.05,
) -> tuple[list[RetrievalHit], list[RetrievalHit]]:
    """混合检索：向量相似度 + 关键词匹配。

    Returns:
        (allowed_hits, denied_hits)
    """
    docs = db.query(KnowledgeDoc).all()
    if not docs:
        return [], []

    query_embedding = _compute_embedding(query)
    query_tokens = _tokenize(query)

    hits = []
    for doc in docs:
        vec_score = 0.0
        if query_embedding and doc.embedding:
            vec_score = _cosine_similarity(query_embedding, doc.embedding)

        kw_score = _keyword_score(query, doc)
        # 归一化关键词分数到 0-1 范围（假设最大原始分为 20）
        kw_score_norm = min(kw_score / 20.0, 1.0)

        score = vector_weight * vec_score + keyword_weight * kw_score_norm

        if score < min_score:
            continue

        allowed = ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER.get(doc.min_role, 999)
        hits.append(RetrievalHit(doc=doc, score=score, allowed=allowed))

    hits.sort(key=lambda h: h.score, reverse=True)
    allowed_hits = [h for h in hits if h.allowed][:top_k]
    denied_hits = [h for h in hits if not h.allowed][:top_k]
    return allowed_hits, denied_hits


def get_visible_knowledge(db: Session, user_role: str) -> list[dict]:
    docs = db.query(KnowledgeDoc).all()
    visible = []
    for doc in docs:
        if ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER.get(doc.min_role, 999):
            visible.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "min_role": doc.min_role,
                    "sensitivity": doc.sensitivity,
                    "keywords": doc.keywords,
                }
            )
    return visible
