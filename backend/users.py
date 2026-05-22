from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


ROLE_ORDER = {
    "public": 0,
    "student": 1,
    "teacher": 2,
    "admin": 3,
}


@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    role: str


def _derive_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


_ACCOUNTS = {
    "alice": {
        "display_name": "陈爱丽",
        "role": "student",
        "salt": "course-demo-student",
        "password_hash": _derive_password("student123", "course-demo-student"),
    },
    "prof": {
        "display_name": "王教授",
        "role": "teacher",
        "salt": "course-demo-teacher",
        "password_hash": _derive_password("teacher123", "course-demo-teacher"),
    },
    "admin": {
        "display_name": "安全管理员",
        "role": "admin",
        "salt": "course-demo-admin",
        "password_hash": _derive_password("admin123", "course-demo-admin"),
    },
}


def role_allows(user_role: str, min_role: str) -> bool:
    return ROLE_ORDER.get(user_role, -1) >= ROLE_ORDER.get(min_role, 999)


def authenticate(username: str, password: str) -> User | None:
    account = _ACCOUNTS.get(username.strip())
    if account is None:
        return None
    candidate = _derive_password(password, account["salt"])
    if not hmac.compare_digest(candidate, account["password_hash"]):
        return None
    return User(
        username=username.strip(),
        display_name=account["display_name"],
        role=account["role"],
    )


def public_profile(user: User) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }
