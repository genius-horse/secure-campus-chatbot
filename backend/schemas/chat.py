from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str = ""
    clear_history: bool = False


class ChatResponse(BaseModel):
    action: str
    risk: str
    answer: str
    policy_hits: list[dict]
    citations: list[dict]
    denied_citations: list[dict]
    audit_id: Optional[int]
    generation_mode: str
    llm_error: Optional[str]
    history_message_count: int
    history_cleared: Optional[bool] = None
