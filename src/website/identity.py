from typing import Any

from fastapi import Request
from fastapi_permissions import Authenticated, Everyone


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
