from pydantic import BaseModel
from typing import Optional


class KnowledgeItem(BaseModel):
    id: str
    title: str
    min_role: str
    sensitivity: str
    keywords: list[str]


class KnowledgeDetail(KnowledgeItem):
    content: str


class KnowledgeManageRequest(BaseModel):
    action: str = "list"
    id: Optional[str] = None
    title: Optional[str] = None
    min_role: Optional[str] = None
    sensitivity: Optional[str] = None
    keywords: Optional[list[str]] = None
    content: Optional[str] = None
