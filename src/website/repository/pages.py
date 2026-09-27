"""Editable static page persistence."""

from website.db import Connection
from website.models import StaticPage
from website.repository._rows import fetch_one, require

_PAGE_SELECT = "SELECT id, slug, content, updated_at, updated_by_id FROM static_pages"


def get_static_page(db: Connection, slug: str) -> StaticPage | None:
    """Return the static page with *slug*, or None."""
    return fetch_one(db, StaticPage, f"{_PAGE_SELECT} WHERE slug = ?", [slug])


def upsert_static_page(
    db: Connection, slug: str, content: str, updated_by_id: int | None = None
) -> StaticPage:
    """Create or replace a static page's content and return it."""
    db.execute(
        "INSERT INTO static_pages (slug, content, updated_by_id)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT (slug) DO UPDATE"
        " SET content = excluded.content,"
        "     updated_at = now(),"
        "     updated_by_id = excluded.updated_by_id",
        [slug, content, updated_by_id],
    )
    return require(get_static_page(db, slug), "static page")
