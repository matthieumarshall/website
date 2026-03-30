import hashlib
import base64
from typing import Any

import bcrypt
from fastapi import Request
from fastapi_permissions import Authenticated, Everyone


def _prepare(plain_password: str) -> bytes:
    """SHA-256 pre-hash so bcrypt's 72-byte limit is never hit."""
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(_prepare(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))


def get_current_user(request: Request) -> dict[str, Any] | None:
    """Return the session user dict or None if not authenticated."""
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    role = request.session.get("role")
    if user_id and username and role:
        return {"id": user_id, "username": username, "role": role}
    return None


def get_active_principals(request: Request) -> list[str]:
    """Return the fastapi-permissions principal list for the current request."""
    user = get_current_user(request)
    if user:
        return [
            Everyone,
            Authenticated,
            f"role:{user['role']}",
            f"user:{user['id']}",
        ]
    return [Everyone]
