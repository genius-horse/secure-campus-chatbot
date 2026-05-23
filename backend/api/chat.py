from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, get_client_ip
from schemas.chat import ChatRequest
from services.chat_service import respond
from models.user import User

router = APIRouter()

# 内存中维护会话历史（简化方案；生产环境应使用 Redis）
CONVERSATIONS: dict[str, list[dict]] = {}
MAX_HISTORY_LENGTH = 20


@router.post("/chat")
def chat(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

    # 纯清除历史请求
    if payload.clear_history and not payload.message.strip():
        CONVERSATIONS.pop(token, None)
        return {
            "action": "allowed",
            "risk": "none",
            "answer": "",
            "policy_hits": [],
            "citations": [],
            "denied_citations": [],
            "audit_id": None,
            "generation_mode": "local",
            "llm_error": None,
            "history_message_count": 0,
            "history_cleared": True,
        }

    message = payload.message
    if len(message) > 5000:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="消息过长，最大允许5000个字符。")

    # 获取历史
    if payload.clear_history:
        CONVERSATIONS.pop(token, None)
    history = CONVERSATIONS.get(token, [])

    # 调用服务
    result = respond(
        db,
        user=user,
        message=message,
        history=history if history else None,
        client_ip=get_client_ip(request),
    )

    # 更新历史（仅允许通过的请求）
    if result["action"] != "blocked" and token:
        conv = CONVERSATIONS.setdefault(token, [])
        conv.append({"role": "user", "content": message})
        conv.append({"role": "assistant", "content": result["answer"]})
        if len(conv) > MAX_HISTORY_LENGTH * 2:
            CONVERSATIONS[token] = conv[-(MAX_HISTORY_LENGTH * 2):]

    return result
