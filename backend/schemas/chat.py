from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    message: str = ""
    clear_history: bool = False
    session_id: Optional[str] = None
    web_enabled: bool = False


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
    session_id: Optional[str] = None


class SessionCreate(BaseModel):
    name: str = Field(default="新会话", min_length=1, max_length=100)


class SessionRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RegenerateRequest(BaseModel):
    session_id: Optional[str] = None
