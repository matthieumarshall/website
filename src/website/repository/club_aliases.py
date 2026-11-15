"""Persistence for staff-maintained imported club names."""

from website.db import Connection
from website.models.competition import ClubAlias
from website.repository._rows import fetch_all


def list_aliases(db: Connection) -> list[ClubAlias]:
    """Return all club aliases."""
    return fetch_all(
        db, ClubAlias, "SELECT id, club_id, name FROM club_aliases ORDER BY name"
    )


def add_alias(db: Connection, club_id: int, name: str) -> None:
    """Associate an imported name with a club."""
    db.execute(
        "INSERT INTO club_aliases (club_id, name) VALUES (?, ?)", [club_id, name]
    )


def remove_alias(db: Connection, alias_id: int) -> None:
    """Remove a mapping without changing imported results."""
    db.execute("DELETE FROM club_aliases WHERE id = ?", [alias_id])


def imported_club_names(db: Connection) -> list[str]:
    """Return distinct names used in results and team standings."""
    rows = db.execute(
        "SELECT DISTINCT club FROM results WHERE club IS NOT NULL "
        "UNION SELECT DISTINCT club FROM team_standings WHERE club IS NOT NULL "
        "UNION SELECT DISTINCT club FROM team_round_results WHERE club IS NOT NULL "
        "ORDER BY club"
    ).fetchall()
    return [row[0] for row in rows]
