import json as _json
import logging
import re
import secrets
from typing import Any
from urllib.parse import urlparse

import httpx
import nh3
from fastapi import HTTPException, Request

_logger = logging.getLogger(__name__)

from website.identity import get_current_user  # noqa: E402
from website.models import TimetableEntry, UserRole  # noqa: E402

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
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "colgroup",
    "col",
    "span",
}
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "aria-label"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "data-row", "data-cell"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"width"},
    "table": {"class"},
    "span": {"class", "data-row", "data-cell"},
}

ADMIN_GUIDES: dict[str, dict[str, str]] = {
    "athlete-registration-guide": {
        "title": "Athlete Registration Guide",
        "slug": "athlete-registration-guide",
        "page": "athlete_registration_guide",
        "route": "/administration/athlete-registration-guide",
        "filename": "athlete-registration-guide.pdf",
    },
    "race-directors-guide": {
        "title": "Race Directors Guide",
        "slug": "race-directors-guide",
        "page": "race_directors_guide",
        "route": "/administration/race-directors-guide",
        "filename": "race-directors-guide.pdf",
    },
    "suppliers-list": {
        "title": "Suppliers List",
        "slug": "suppliers-list",
        "page": "suppliers_list",
        "route": "/administration/suppliers-list",
        "filename": "suppliers-list.pdf",
    },
    "team-managers-guide": {
        "title": "Team Managers Guide",
        "slug": "team-managers-guide",
        "page": "team_managers_guide",
        "route": "/administration/team-managers-guide",
        "filename": "team-managers-guide.pdf",
    },
}

SIDEBAR_ITEMS: list[dict[str, Any]] = [
    {"name": "Home / News", "route": "/news", "page": "news"},
    {"name": "Results", "route": "/results", "page": "results"},
    {"name": "Standings", "route": "/standings", "page": "standings"},
    {"name": "Divisions", "route": "/divisions", "page": "divisions"},
    {"name": "Past Winners", "route": "/winners", "page": "winners"},
    {"name": "Member Clubs", "route": "/clubs", "page": "clubs"},
    {
        "name": "Rules and Constitution",
        "route": "/rules-and-constitution",
        "page": "rules_and_constitution",
    },
    {
        "name": "Administration",
        "route": "/administration",
        "page": "administration",
        "children": [
            {"name": "Documents", "route": "/administration", "page": "administration"},
            {"name": "Links", "route": "/links", "page": "links"},
            {
                "name": "Athlete Registration Guide",
                "route": "/administration/athlete-registration-guide",
                "page": "athlete_registration_guide",
            },
            {
                "name": "Race Directors Guide",
                "route": "/administration/race-directors-guide",
                "page": "race_directors_guide",
            },
            {
                "name": "Suppliers List",
                "route": "/administration/suppliers-list",
                "page": "suppliers_list",
            },
            {
                "name": "Team Managers Guide",
                "route": "/administration/team-managers-guide",
                "page": "team_managers_guide",
            },
        ],
    },
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


def validate_http_url(value: str) -> str:
    """Validate and return a public HTTP(S) URL."""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an HTTP or HTTPS URL")
    return value.strip()


def page_context(request: Request, current_page: str, **extra: Any) -> dict[str, Any]:
    return {
        "current_user": get_current_user(request),
        "current_page": current_page,
        "sidebar_items": SIDEBAR_ITEMS,
        "csrf_token": get_csrf_token(request),
        "show_cookie_notice": not request.cookies.get("cookie_notice_dismissed"),
        "UserRole": UserRole,
        **extra,
    }


def sanitise_html(raw: str) -> str:
    return nh3.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def post_summary(content: str, post_id: int, length: int = 300) -> str:
    """Return an HTML summary of post content truncated at a word boundary.

    If the post is longer than length, it is truncated and an inline
    '... see more' link pointing to /news/{post_id} is appended.
    Unclosed HTML tags are safely balanced via sanitise_html.
    """
    if not content:
        return ""

    plain = re.sub(r"<[^>]+>", "", content).strip()
    if len(content) <= length or (
        len(plain) <= length and len(content) <= length + 100
    ):
        return content

    sliced = content[:length]
    sliced = re.sub(r"<[^>]*$", "", sliced)
    if " " in sliced:
        sliced = sliced.rsplit(" ", 1)[0]
    sliced = re.sub(r"<[^>]*$", "", sliced)
    sliced = sliced.rstrip(".,;:!? \t\n")

    clean_body = sanitise_html(sliced)
    link = (
        f'... <a href="/news/{post_id}" aria-label="See more of this post">see more</a>'
    )

    closing_tags = ("</p>", "</blockquote>", "</li>", "</div>")
    for tag in closing_tags:
        if clean_body.endswith(tag):
            idx = len(clean_body) - len(tag)
            body_without_tag = clean_body[:idx].rstrip(".,;:!? \t\n")
            return body_without_tag + link + tag

    return f"{clean_body}{link}"


def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode an address string to (latitude, longitude) using the Nominatim API.

    Returns a (lat, lon) tuple on success, or None if the address cannot be found
    or the request fails. Nominatim's usage policy requires a descriptive User-Agent.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": "1"},
                headers={
                    "User-Agent": "FixtureWebsite/1.0 (fixture location geocoder)"
                },
            )
            response.raise_for_status()
            results = response.json()
            if results:
                return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception:
        _logger.warning("Failed to geocode address: %s", address)
    return None


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
