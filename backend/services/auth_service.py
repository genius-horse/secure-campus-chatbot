import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from core.constants import ROLE_ORDER
from core.exceptions import AuthenticationException
from models.user import User


def derive_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def role_allows(user_role: str, min_role: str) -> bool:
    return ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER.get(min_role, 999)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    username = username.strip()
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    candidate = derive_password(password, user.salt)
    if not hmac.compare_digest(candidate, user.password_hash):
        return None
    return user


def create_access_token(user: User) -> str:
    to_encode = {
        "sub": user.username,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


def get_user_from_token(db: Session, token: str) -> Optional[User]:
    payload = decode_token(token)
    if payload is None:
        return None
    username = payload.get("sub")
    if username is None:
        return None
    return db.query(User).filter(User.username == username).first()


def public_profile(user: User) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }
