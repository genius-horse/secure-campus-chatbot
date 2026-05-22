from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from users import role_allows


ROOT_DIR = Path(__file__).resolve().parents[1]
KB_PATH = ROOT_DIR / "data" / "campus_kb.json"

_KB_LOCK = Lock()


@dataclass(frozen=True)
class KnowledgeDoc:
    id: str
    title: str
    min_role: str
    sensitivity: str
    keywords: list[str]
    content: str


@dataclass(frozen=True)
class RetrievalHit:
    doc: KnowledgeDoc
    score: int
    allowed: bool


def load_knowledge(path: Path = KB_PATH) -> list[KnowledgeDoc]:
    raw_docs = json.loads(path.read_text(encoding="utf-8"))
    return [KnowledgeDoc(**item) for item in raw_docs]


def _save_knowledge(docs: list[KnowledgeDoc], path: Path = KB_PATH) -> None:
    with _KB_LOCK:
        raw = []
        for doc in docs:
            raw.append({
                "id": doc.id,
                "title": doc.title,
                "min_role": doc.min_role,
                "sensitivity": doc.sensitivity,
                "keywords": doc.keywords,
                "content": doc.content,
            })
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def add_knowledge(
    id: str,
    title: str,
    min_role: str,
    sensitivity: str,
    keywords: list[str],
    content: str,
) -> KnowledgeDoc:
    docs = load_knowledge()
    if any(d.id == id for d in docs):
        raise ValueError(f"知识条目 '{id}' 已存在")
    doc = KnowledgeDoc(
        id=id,
        title=title,
        min_role=min_role,
        sensitivity=sensitivity,
        keywords=keywords,
        content=content,
    )
    docs.append(doc)
    _save_knowledge(docs)
    return doc


def update_knowledge(
    id: str,
    title: str | None = None,
    min_role: str | None = None,
    sensitivity: str | None = None,
    keywords: list[str] | None = None,
    content: str | None = None,
) -> KnowledgeDoc:
    docs = load_knowledge()
    for i, d in enumerate(docs):
        if d.id == id:
            updated = KnowledgeDoc(
                id=id,
                title=title if title is not None else d.title,
                min_role=min_role if min_role is not None else d.min_role,
                sensitivity=sensitivity if sensitivity is not None else d.sensitivity,
                keywords=keywords if keywords is not None else d.keywords,
                content=content if content is not None else d.content,
            )
            docs[i] = updated
            _save_knowledge(docs)
            return updated
    raise ValueError(f"知识条目 '{id}' 不存在")


def delete_knowledge(id: str) -> None:
    docs = load_knowledge()
    new_docs = [d for d in docs if d.id != id]
    if len(new_docs) == len(docs):
        raise ValueError(f"知识条目 '{id}' 不存在")
    _save_knowledge(new_docs)


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
    return words | chinese_terms


def _score(query: str, doc: KnowledgeDoc) -> int:
    q = query.lower()
    q_tokens = _tokens(query)
    searchable = f"{doc.title} {' '.join(doc.keywords)} {doc.content}".lower()
    doc_tokens = _tokens(searchable)
    score = len(q_tokens & doc_tokens)
    for keyword in doc.keywords:
        if keyword.lower() in q:
            score += 4
    if any(part in searchable for part in q_tokens):
        score += 1
    return score


def search(query: str, user_role: str, limit: int = 3) -> tuple[list[RetrievalHit], list[RetrievalHit]]:
    hits: list[RetrievalHit] = []
    for doc in load_knowledge():
        score = _score(query, doc)
        if score <= 0:
            continue
        allowed = role_allows(user_role, doc.min_role)
        hits.append(RetrievalHit(doc=doc, score=score, allowed=allowed))

    hits.sort(key=lambda item: item.score, reverse=True)
    allowed_hits = [item for item in hits if item.allowed][:limit]
    denied_hits = [item for item in hits if not item.allowed][:limit]
    return allowed_hits, denied_hits


def visible_knowledge(user_role: str) -> list[dict]:
    docs = load_knowledge()
    visible = []
    for doc in docs:
        if role_allows(user_role, doc.min_role):
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
