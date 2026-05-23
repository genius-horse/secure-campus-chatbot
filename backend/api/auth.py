import time
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user, get_client_ip
from schemas.auth import LoginRequest
from services.auth_service import authenticate_user, create_access_token, public_profile
from models.user import User

router = APIRouter()

# Simple in-memory rate limiter: 10 attempts per minute per IP
_login_attempts: dict[str, deque[float]] = {}
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 60


def _check_rate_limit(ip: str) -> bool:
    now = time.monotonic()
    window = _login_attempts.setdefault(ip, deque())
    # Remove old attempts
    while window and window[0] < now - WINDOW_SECONDS:
        window.popleft()
    return len(window) < MAX_ATTEMPTS


def _record_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, deque()).append(time.monotonic())


@router.post("/login")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试次数过多，请稍后再试。",
        )
    _record_attempt(ip)

    username = payload.username.strip()
    password = payload.password
    if len(username) > 64 or len(password) > 128:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    user = authenticate_user(db, username, password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token(user)
    return {"token": token, "user": public_profile(user)}


@router.post("/logout")
def logout():
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": public_profile(user)}
