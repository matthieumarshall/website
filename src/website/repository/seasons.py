"""Season persistence."""

from website.db import Connection
from website.models import Season
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

_SEASON_SELECT = "SELECT id, name, created_at FROM seasons"


def list_seasons(db: Connection) -> list[Season]:
    """Return all seasons, most recent name first."""
    return fetch_all(db, Season, f"{_SEASON_SELECT} ORDER BY name DESC")


def get_season_by_id(db: Connection, season_id: int) -> Season | None:
    """Return the season with *season_id*, or None."""
    return fetch_one(db, Season, f"{_SEASON_SELECT} WHERE id = ?", [season_id])


def create_season(db: Connection, name: str) -> Season:
    """Insert a season and return it."""
    db.execute("INSERT INTO seasons (name) VALUES (?)", [name])
    season = fetch_one(db, Season, f"{_SEASON_SELECT} WHERE name = ?", [name])
    return require(season, "season")


def delete_season(db: Connection, season_id: int) -> bool:
    """Delete an empty season.

    Raises:
        ValueError: If the season still has fixtures.
    """
    count = fetch_count(
        db, "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    )
    if count > 0:
        raise ValueError(
            f"Cannot delete season {season_id}: it still has {count} fixture(s). "
            "Delete all fixtures first."
        )
    db.execute("DELETE FROM seasons WHERE id = ?", [season_id])
    return True
