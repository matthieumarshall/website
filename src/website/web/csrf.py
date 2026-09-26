"""Synchronizer-token CSRF protection for form posts."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request

_SESSION_KEY = "csrf_token"
_FORM_FIELD = "csrf_token"


def get_csrf_token(request: Request) -> str:
    """Return the session's CSRF token, creating one if needed."""
    token = request.session.get(_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_hex(32)
        request.session[_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, form_token: str) -> None:
    """Check a submitted token against the session.

    Raises:
        HTTPException: 403 if the token is missing or wrong.
    """
    expected = request.session.get(_SESSION_KEY)
    if not isinstance(expected, str) or not secrets.compare_digest(
        expected.encode(), form_token.encode()
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def verify_csrf(request: Request) -> None:
    """Dependency: validate the ``csrf_token`` field of the posted form.

    Starlette caches the parsed form, so the endpoint can still bind fields.

    Raises:
        HTTPException: 403 if the token is missing or wrong.
    """
    form = await request.form()
    token = form.get(_FORM_FIELD)
    validate_csrf(request, token if isinstance(token, str) else "")


CsrfProtected = Annotated[None, Depends(verify_csrf)]
