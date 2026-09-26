"""Club and club manager persistence."""

from website.db import Connection
from website.models import Club, ClubManager, ClubManagerListing
from website.repository._rows import (
    fetch_all,
    fetch_count,
    fetch_one,
    fetch_value,
    require,
)

_CLUB_SELECT = (
    "SELECT id, name, oxl_code, ea_club_id, is_active, opentrack_code,"
    " website_url, is_oxfordshire_member FROM clubs"
)


def list_clubs(db: Connection) -> list[Club]:
    """Return every club, alphabetically."""
    return fetch_all(db, Club, f"{_CLUB_SELECT} ORDER BY name")


def list_public_clubs(db: Connection) -> list[Club]:
    """Return active clubs suitable for the public member directory."""
    return [club for club in list_clubs(db) if club.is_active]


def get_club_by_id(db: Connection, club_id: int) -> Club | None:
    """Return the club with *club_id*, or None."""
    return fetch_one(db, Club, f"{_CLUB_SELECT} WHERE id = ?", [club_id])


def create_club(
    db: Connection,
    name: str,
    oxl_code: str,
    ea_club_id: str,
    opentrack_code: str | None = None,
    website_url: str | None = None,
    is_oxfordshire_member: bool = True,
) -> Club:
    """Insert a club and return it.

    Raises:
        duckdb.ConstraintException: If the OXL code is already used.
    """
    db.execute(
        "INSERT INTO clubs (name, oxl_code, ea_club_id, opentrack_code,"
        " website_url, is_oxfordshire_member) VALUES (?, ?, ?, ?, ?, ?)",
        [
            name,
            oxl_code,
            ea_club_id,
            opentrack_code,
            website_url,
            is_oxfordshire_member,
        ],
    )
    club = fetch_one(db, Club, f"{_CLUB_SELECT} WHERE oxl_code = ?", [oxl_code])
    return require(club, "club")


def update_club(  # noqa: PLR0913 — one parameter per club column
    db: Connection,
    club_id: int,
    name: str,
    oxl_code: str,
    ea_club_id: str,
    is_active: bool,
    opentrack_code: str | None = None,
    website_url: str | None = None,
    is_oxfordshire_member: bool = True,
) -> None:
    """Update every editable field of a club."""
    db.execute(
        "UPDATE clubs SET name = ?, oxl_code = ?, ea_club_id = ?, is_active = ?,"
        " opentrack_code = ?, website_url = ?, is_oxfordshire_member = ? WHERE id = ?",
        [
            name,
            oxl_code,
            ea_club_id,
            is_active,
            opentrack_code,
            website_url,
            is_oxfordshire_member,
            club_id,
        ],
    )


def toggle_club_active(db: Connection, club_id: int) -> None:
    """Flip a club's active flag."""
    db.execute("UPDATE clubs SET is_active = NOT is_active WHERE id = ?", [club_id])


def club_has_active_batches(db: Connection, club_id: int) -> bool:
    """Return True if the club has any pending or paid entry batches."""
    count = fetch_count(
        db,
        "SELECT COUNT(*) FROM entry_batches WHERE club_id = ?"
        " AND status IN ('pending_payment', 'payment_initiated', 'paid')",
        [club_id],
    )
    return count > 0


def list_club_managers(db: Connection) -> list[ClubManagerListing]:
    """Return every club manager with their club and username."""
    return fetch_all(
        db,
        ClubManagerListing,
        """
        SELECT cm.id AS manager_id, cm.user_id, cm.club_id, cm.is_active,
               c.name AS club_name, u.username, cm.email
        FROM club_managers cm
        JOIN clubs c ON c.id = cm.club_id
        JOIN users u ON u.id = cm.user_id
        ORDER BY c.name, u.username
        """,
    )


def get_club_for_manager(db: Connection, user_id: int) -> ClubManager | None:
    """Return the club manager record for a user, or None."""
    return fetch_one(
        db,
        ClubManager,
        """
        SELECT cm.id, cm.user_id, cm.club_id, cm.is_active, c.name AS club_name
        FROM club_managers cm
        JOIN clubs c ON c.id = cm.club_id
        WHERE cm.user_id = ?
        """,
        [user_id],
    )


def create_club_manager(
    db: Connection, user_id: int, club_id: int, email: str | None = None
) -> None:
    """Link a user to the club they manage."""
    db.execute(
        "INSERT INTO club_managers (user_id, club_id, email) VALUES (?, ?, ?)",
        [user_id, club_id, email],
    )


def get_club_manager_email(db: Connection, user_id: int) -> str | None:
    """Return a club manager's contact email, if recorded."""
    value = fetch_value(
        db, "SELECT email FROM club_managers WHERE user_id = ?", [user_id]
    )
    return value if isinstance(value, str) else None


def toggle_club_manager_active(db: Connection, manager_id: int) -> bool:
    """Flip ``is_active`` for a club manager and return the new value."""
    current = fetch_value(
        db, "SELECT is_active FROM club_managers WHERE id = ?", [manager_id]
    )
    if current is None:
        return False
    new_value = not current
    db.execute(
        "UPDATE club_managers SET is_active = ? WHERE id = ?", [new_value, manager_id]
    )
    return new_value
