"""The signed-in user, as stored in the session cookie."""

from fastapi import Request
from fastapi_permissions import Authenticated, Everyone

from website.models import CurrentUser, User

_SESSION_KEYS = ("user_id", "username", "role")


def get_current_user(request: Request) -> CurrentUser | None:
    """Return the session user, or None if not signed in."""
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    role = request.session.get("role")
    if user_id and username and role:
        return CurrentUser(id=user_id, username=username, role=role)
    return None


def get_active_principals(request: Request) -> list[str]:
    """Return the fastapi-permissions principals for the current request."""
    user = get_current_user(request)
    if user is None:
        return [Everyone]
    return [Everyone, Authenticated, f"role:{user.role}", f"user:{user.id}"]


def is_staff(request: Request) -> bool:
    """Return True if an admin or content creator is signed in."""
    user = get_current_user(request)
    return user is not None and user.is_staff


def sign_in(request: Request, user: User) -> None:
    """Start a fresh session for *user* (clearing any old session first)."""
    # Session fixation: clear before setting new user session data
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role.value


def sign_out(request: Request) -> None:
    """End the current session."""
    request.session.clear()
