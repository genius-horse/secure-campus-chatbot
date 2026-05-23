import uuid
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, get_client_ip
from schemas.chat import ChatRequest, SessionCreate, SessionRename, RegenerateRequest
from services.web_search import is_configured as web_search_configured
from services.chat_service import respond
from models.user import User

router = APIRouter()

# ── In-memory session store ──
SESSIONS_STORE: dict[str, dict] = {}     # session_id -> {id, name, messages, created_at, updated_at}
USER_SESSIONS: dict[str, list[str]] = {}  # username -> [session_id, ...]
ACTIVE_SESSION: dict[str, str] = {}       # username -> active_session_id
MAX_HISTORY_LENGTH = 20
MAX_SESSIONS_PER_USER = 50


def _user_key(user: User) -> str:
    return user.username


def _get_or_create_active_session(username: str) -> str:
    sid = ACTIVE_SESSION.get(username)
    if sid and sid in SESSIONS_STORE:
        return sid
    sid = _create_session(username, "新会话")
    ACTIVE_SESSION[username] = sid
    return sid


def _create_session(username: str, name: str) -> str:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    SESSIONS_STORE[sid] = {
        "id": sid,
        "name": name,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    USER_SESSIONS.setdefault(username, []).append(sid)
    # Limit sessions per user
    if len(USER_SESSIONS[username]) > MAX_SESSIONS_PER_USER:
        oldest = USER_SESSIONS[username].pop(0)
        SESSIONS_STORE.pop(oldest, None)
        if ACTIVE_SESSION.get(username) == oldest:
            ACTIVE_SESSION.pop(username, None)
    return sid


def _cleanup_orphan_sessions():
    """Remove sessions not referenced by any user."""
    referenced = set()
    for sids in USER_SESSIONS.values():
        referenced.update(sids)
    orphans = [sid for sid in SESSIONS_STORE if sid not in referenced]
    for sid in orphans:
        SESSIONS_STORE.pop(sid, None)


# ── Session CRUD endpoints ──

@router.get("/sessions")
def list_sessions(user: User = Depends(get_current_user)):
    username = _user_key(user)
    sids = USER_SESSIONS.get(username, [])
    sessions = []
    active = ACTIVE_SESSION.get(username)
    for sid in reversed(sids):
        s = SESSIONS_STORE.get(sid)
        if s:
            sessions.append({
                "id": s["id"],
                "name": s["name"],
                "message_count": len(s["messages"]),
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "is_active": sid == active,
            })
    return {"sessions": sessions, "active_session_id": active}


@router.post("/sessions")
def create_session(
    payload: SessionCreate,
    user: User = Depends(get_current_user),
):
    username = _user_key(user)
    sid = _create_session(username, payload.name)
    ACTIVE_SESSION[username] = sid
    return {
        "id": sid,
        "name": payload.name,
        "message_count": 0,
        "created_at": SESSIONS_STORE[sid]["created_at"],
        "updated_at": SESSIONS_STORE[sid]["updated_at"],
        "is_active": True,
    }


@router.put("/sessions/{session_id}")
def rename_session(
    session_id: str,
    payload: SessionRename,
    user: User = Depends(get_current_user),
):
    username = _user_key(user)
    if session_id not in USER_SESSIONS.get(username, []):
        raise HTTPException(status_code=404, detail="会话不存在")
    s = SESSIONS_STORE.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    s["name"] = payload.name
    s["updated_at"] = time.time()
    return {"ok": True, "name": payload.name}


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
):
    username = _user_key(user)
    if session_id not in USER_SESSIONS.get(username, []):
        raise HTTPException(status_code=404, detail="会话不存在")
    USER_SESSIONS[username].remove(session_id)
    SESSIONS_STORE.pop(session_id, None)
    if ACTIVE_SESSION.get(username) == session_id:
        ACTIVE_SESSION.pop(username, None)
        # Activate the most recent remaining session, or create a new one
        remaining = USER_SESSIONS.get(username, [])
        if remaining:
            ACTIVE_SESSION[username] = remaining[-1]
        else:
            _get_or_create_active_session(username)
    return {"ok": True, "active_session_id": ACTIVE_SESSION.get(username)}


@router.post("/sessions/{session_id}/activate")
def activate_session(
    session_id: str,
    user: User = Depends(get_current_user),
):
    username = _user_key(user)
    if session_id not in USER_SESSIONS.get(username, []):
        raise HTTPException(status_code=404, detail="会话不存在")
    ACTIVE_SESSION[username] = session_id
    s = SESSIONS_STORE.get(session_id, {})
    messages = s.get("messages", [])
    return {
        "ok": True,
        "session_id": session_id,
        "session_name": s.get("name", ""),
        "messages": messages,
    }


# ── Streaming chat endpoint ──

@router.post("/chat/stream")
def chat_stream(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import json
    from fastapi.responses import StreamingResponse
    from services.chat_service import respond_stream

    username = _user_key(user)

    # Determine session
    session_id = payload.session_id or _get_or_create_active_session(username)
    if session_id not in SESSIONS_STORE:
        session_id = _get_or_create_active_session(username)
    ACTIVE_SESSION[username] = session_id

    s = SESSIONS_STORE[session_id]

    if len(payload.message) > 5000:
        raise HTTPException(status_code=400, detail="消息过长，最大允许5000个字符。")

    if payload.clear_history:
        s["messages"] = []

    history = s.get("messages", [])

    def event_stream():
        full_answer = ""
        final_meta = {}

        try:
            for event in respond_stream(
                db, user=user, message=payload.message,
                history=history if history else None,
                client_ip=get_client_ip(request),
                web_enabled=payload.web_enabled,
            ):
                if event.get("type") == "meta":
                    event["session_id"] = session_id
                if event.get("type") == "token":
                    full_answer += (event.get("token") or "")
                if event.get("type") == "done":
                    final_meta = event
                    event["session_id"] = session_id
                    full_answer = event.get("answer", full_answer)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

        # Update session history
        final_action = final_meta.get("action", "allowed")
        if final_action != "blocked" and full_answer:
            s["messages"].append({"role": "user", "content": payload.message})
            s["messages"].append({"role": "assistant", "content": full_answer})
            if len(s["messages"]) > MAX_HISTORY_LENGTH * 2:
                s["messages"] = s["messages"][-(MAX_HISTORY_LENGTH * 2):]
            s["updated_at"] = time.time()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "close",
            "X-Accel-Buffering": "no",
        },
    )


# ── Chat endpoint ──

@router.post("/chat")
def chat(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    username = _user_key(user)

    # Determine session
    session_id = payload.session_id or _get_or_create_active_session(username)
    if session_id not in SESSIONS_STORE:
        session_id = _get_or_create_active_session(username)
    ACTIVE_SESSION[username] = session_id

    s = SESSIONS_STORE[session_id]

    # Pure clear history
    if payload.clear_history and not payload.message.strip():
        s["messages"] = []
        s["updated_at"] = time.time()
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
            "session_id": session_id,
        }

    message = payload.message
    if len(message) > 5000:
        raise HTTPException(status_code=400, detail="消息过长，最大允许5000个字符。")

    # Handle clear_history flag
    if payload.clear_history:
        s["messages"] = []

    history = s.get("messages", [])

    # Call service
    result = respond(
        db,
        user=user,
        message=message,
        history=history if history else None,
        client_ip=get_client_ip(request),
        web_enabled=payload.web_enabled,
    )

    # Update session history (only for allowed requests)
    if result["action"] != "blocked":
        s["messages"].append({"role": "user", "content": message})
        s["messages"].append({"role": "assistant", "content": result["answer"]})
        if len(s["messages"]) > MAX_HISTORY_LENGTH * 2:
            s["messages"] = s["messages"][-(MAX_HISTORY_LENGTH * 2):]
        s["updated_at"] = time.time()

    result["session_id"] = session_id
    return result


# ── Regenerate endpoint ──

@router.post("/chat/regenerate")
def regenerate(
    request: Request,
    payload: RegenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    username = _user_key(user)
    session_id = payload.session_id or ACTIVE_SESSION.get(username)
    if not session_id or session_id not in SESSIONS_STORE:
        raise HTTPException(status_code=404, detail="没有活跃会话")

    s = SESSIONS_STORE[session_id]
    messages = s.get("messages", [])

    # Find last user message
    last_user_msg = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_msg = messages[i]["content"]
            # Remove last assistant reply if exists
            if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                messages.pop(i + 1)
            break

    if not last_user_msg:
        raise HTTPException(status_code=400, detail="没有可重新生成的消息")

    # Build history up to (but not including) the last user message
    history = messages[:i] if i > 0 else None

    result = respond(
        db,
        user=user,
        message=last_user_msg,
        history=history,
        client_ip=get_client_ip(request),
        web_enabled=False,
    )

    if result["action"] != "blocked":
        messages.append({"role": "assistant", "content": result["answer"]})
        s["updated_at"] = time.time()

    result["session_id"] = session_id
    return result
