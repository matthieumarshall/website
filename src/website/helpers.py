import json as _json
import secrets
from typing import Any
from urllib.parse import urlparse

import nh3
from fastapi import HTTPException, Request

from website.identity import get_current_user
from website.models import TimetableEntry

# Allowed HTML tags / attributes for sanitised post content
_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "img",
}
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height"},
}

SIDEBAR_ITEMS: list[dict[str, str]] = [
    {"name": "Home / News", "route": "/news", "page": "news"},
    {"name": "Results", "route": "/results", "page": "results"},
    {"name": "Entries", "route": "/entries", "page": "entries"},
    {
        "name": "Rules and Constitution",
        "route": "/rules-and-constitution",
        "page": "rules_and_constitution",
    },
    {"name": "Administration", "route": "/administration", "page": "administration"},
    {"name": "Fixtures", "route": "/fixtures", "page": "fixtures"},
]


def get_csrf_token(request: Request) -> str:
    token: str | None = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, form_token: str) -> None:
    expected: str | None = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, form_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def safe_referer_path(referer: str) -> str:
    if not referer:
        return "/news"
    path = urlparse(referer).path
    return path if path and path.startswith("/") else "/news"


def page_context(request: Request, current_page: str, **extra: Any) -> dict[str, Any]:
    return {
        "current_user": get_current_user(request),
        "current_page": current_page,
        "sidebar_items": SIDEBAR_ITEMS,
        "csrf_token": get_csrf_token(request),
        "show_cookie_notice": not request.cookies.get("cookie_notice_dismissed"),
        **extra,
    }


def sanitise_html(raw: str) -> str:
    return nh3.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def parse_timetable_from_json(timetable_json: str) -> list[TimetableEntry]:
    """Deserialise timetable JSON from a form hidden-input field.

    Expects a JSON array of ``{"event": str, "time": str}`` objects.
    Returns a list of ``TimetableEntry`` objects; invalid rows are silently dropped.
    """
    try:
        raw = _json.loads(timetable_json or "[]")
    except ValueError:
        return []
    entries: list[TimetableEntry] = []
    for item in raw:
        if isinstance(item, dict):
            event = str(item.get("event", "")).strip()
            time = str(item.get("time", "")).strip()
            if event or time:
                entries.append(TimetableEntry(event=event, time=time))
    return entries
