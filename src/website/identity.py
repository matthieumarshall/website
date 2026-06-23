from typing import Any

import duckdb
from fastapi import Depends, HTTPException, Request
from fastapi_permissions import Authenticated, Everyone

from website.database import get_db


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


def require_club_manager(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict[str, Any]:
    """FastAPI dependency: require an active club_manager session.

    Returns a dict with keys: user (session dict), club_manager (ClubManager model).
    Raises 403 if the user is not authenticated, not a club_manager, or inactive.
    """
    from website import repository  # avoid circular import at module level

    user = get_current_user(request)
    if user is None or user.get("role") != "club_manager":
        raise HTTPException(status_code=403, detail="Club manager access required")
    club_manager = repository.get_club_for_manager(user["id"], db)
    if club_manager is None or not club_manager.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your club manager account is inactive. Please contact the league.",
        )
    return {"user": user, "club_manager": club_manager}
