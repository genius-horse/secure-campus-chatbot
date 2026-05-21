import json
import re
from dataclasses import dataclass
from pathlib import Path

from users import role_allows


ROOT_DIR = Path(__file__).resolve().parents[1]
KB_PATH = ROOT_DIR / "data" / "campus_kb.json"


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
