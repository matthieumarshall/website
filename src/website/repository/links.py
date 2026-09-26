"""External link persistence."""

from website.db import Connection
from website.models import ExternalLink
from website.repository._rows import fetch_all, fetch_one, require

LINK_CATEGORY_KEYS = ("national", "clubs", "leagues")

_LINK_SELECT = (
    "SELECT id, title, url, category, description, sort_order, is_active"
    " FROM external_links"
)


def _check_category(category: str) -> None:
    if category not in LINK_CATEGORY_KEYS:
        raise ValueError("Invalid link category")


def list_external_links(
    db: Connection, active_only: bool = False
) -> list[ExternalLink]:
    """Return links in display order, optionally hiding inactive records."""
    where = " WHERE is_active = true" if active_only else ""
    return fetch_all(
        db,
        ExternalLink,
        f"{_LINK_SELECT}{where} ORDER BY category, sort_order, title",  # noqa: S608  # nosec B608 — constant clause
    )


def get_external_link(db: Connection, link_id: int) -> ExternalLink | None:
    """Return the link with *link_id*, or None."""
    return fetch_one(db, ExternalLink, f"{_LINK_SELECT} WHERE id = ?", [link_id])  # noqa: S608


def create_external_link(  # noqa: PLR0913 — one parameter per link column
    db: Connection,
    title: str,
    url: str,
    category: str,
    description: str | None,
    sort_order: int,
) -> ExternalLink:
    """Insert an (active) link and return it.

    Raises:
        ValueError: If *category* is not a known link category.
    """
    _check_category(category)
    db.execute(
        "INSERT INTO external_links"
        " (title, url, category, description, sort_order) VALUES (?, ?, ?, ?, ?)",
        [title, url, category, description, sort_order],
    )
    link = fetch_one(
        db,
        ExternalLink,
        f"{_LINK_SELECT} WHERE title = ? AND url = ? ORDER BY id DESC LIMIT 1",  # noqa: S608
        [title, url],
    )
    return require(link, "external link")


def update_external_link(  # noqa: PLR0913 — one parameter per link column
    db: Connection,
    link_id: int,
    title: str,
    url: str,
    category: str,
    description: str | None,
    sort_order: int,
    is_active: bool,
) -> None:
    """Update every editable field of a link.

    Raises:
        ValueError: If *category* is not a known link category.
    """
    _check_category(category)
    db.execute(
        "UPDATE external_links SET title = ?, url = ?, category = ?,"
        " description = ?, sort_order = ?, is_active = ?,"
        " updated_at = current_timestamp WHERE id = ?",
        [title, url, category, description, sort_order, is_active, link_id],
    )


def toggle_external_link(db: Connection, link_id: int) -> None:
    """Flip a link's active flag."""
    db.execute(
        "UPDATE external_links SET is_active = NOT is_active,"
        " updated_at = current_timestamp WHERE id = ?",
        [link_id],
    )


def delete_external_link(db: Connection, link_id: int) -> None:
    """Delete a link."""
    db.execute("DELETE FROM external_links WHERE id = ?", [link_id])
