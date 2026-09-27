"""Winner override persistence and the public winners list."""

from website.db import Connection
from website.models import PublicWinner, WinnerOverride
from website.repository._rows import fetch_all, fetch_one, fetch_value, require

WINNER_TYPES = ("individual", "team")
WINNER_MODES = ("replace", "supplement")

_OVERRIDE_SELECT = (
    "SELECT wo.id, wo.season_id, s.name AS season_name, wo.winner_type,"
    " wo.category, wo.winner_name, wo.club, wo.total_score, wo.note, wo.mode,"
    " wo.is_active, wo.updated_by_id FROM winner_overrides wo"
    " JOIN seasons s ON s.id = wo.season_id"
)


def _check_override(winner_type: str, mode: str) -> None:
    if winner_type not in WINNER_TYPES or mode not in WINNER_MODES:
        raise ValueError("Invalid winner override")


def list_winner_overrides(
    db: Connection, active_only: bool = False
) -> list[WinnerOverride]:
    """Return overrides, newest season first."""
    where = " WHERE wo.is_active = true" if active_only else ""
    return fetch_all(
        db,
        WinnerOverride,
        f"{_OVERRIDE_SELECT}{where}"  # nosec B608 — constant clause
        " ORDER BY s.name DESC, wo.winner_type, wo.category, wo.id",
    )


def get_winner_override(db: Connection, override_id: int) -> WinnerOverride | None:
    """Return the override with *override_id*, or None."""
    return fetch_one(
        db,
        WinnerOverride,
        f"{_OVERRIDE_SELECT} WHERE wo.id = ?",
        [override_id],
    )


def create_winner_override(  # noqa: PLR0913 — one parameter per column
    db: Connection,
    season_id: int,
    winner_type: str,
    category: str,
    winner_name: str,
    club: str | None,
    total_score: int | None,
    note: str | None,
    mode: str,
    updated_by_id: int | None,
) -> WinnerOverride:
    """Insert an override and return it.

    Raises:
        ValueError: If *winner_type* or *mode* is invalid.
    """
    _check_override(winner_type, mode)
    db.execute(
        "INSERT INTO winner_overrides"
        " (season_id, winner_type, category, winner_name, club, total_score,"
        " note, mode, updated_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            season_id,
            winner_type,
            category,
            winner_name,
            club,
            total_score,
            note,
            mode,
            updated_by_id,
        ],
    )
    override_id = fetch_value(
        db,
        "SELECT id FROM winner_overrides WHERE season_id = ?"
        " AND winner_type = ? AND category = ? AND winner_name = ?"
        " ORDER BY id DESC LIMIT 1",
        [season_id, winner_type, category, winner_name],
    )
    override = (
        get_winner_override(db, override_id) if isinstance(override_id, int) else None
    )
    return require(override, "winner override")


def update_winner_override(  # noqa: PLR0913 — one parameter per column
    db: Connection,
    override_id: int,
    season_id: int,
    winner_type: str,
    category: str,
    winner_name: str,
    club: str | None,
    total_score: int | None,
    note: str | None,
    mode: str,
    updated_by_id: int | None,
) -> None:
    """Update every editable field of an override.

    Raises:
        ValueError: If *winner_type* or *mode* is invalid.
    """
    _check_override(winner_type, mode)
    db.execute(
        "UPDATE winner_overrides SET season_id = ?, winner_type = ?, category = ?,"
        " winner_name = ?, club = ?, total_score = ?, note = ?, mode = ?,"
        " updated_by_id = ?, updated_at = current_timestamp WHERE id = ?",
        [
            season_id,
            winner_type,
            category,
            winner_name,
            club,
            total_score,
            note,
            mode,
            updated_by_id,
            override_id,
        ],
    )


def delete_winner_override(db: Connection, override_id: int) -> None:
    """Delete an override."""
    db.execute("DELETE FROM winner_overrides WHERE id = ?", [override_id])


def toggle_winner_override(
    db: Connection, override_id: int, updated_by_id: int | None
) -> None:
    """Flip an override's active flag."""
    db.execute(
        "UPDATE winner_overrides SET is_active = NOT is_active,"
        " updated_by_id = ?, updated_at = current_timestamp WHERE id = ?",
        [updated_by_id, override_id],
    )


def _override_as_winner(override: WinnerOverride) -> PublicWinner:
    return PublicWinner(
        season_name=override.season_name,
        season_id=override.season_id,
        winner_type=override.winner_type,
        category=override.category,
        winner_name=override.winner_name,
        club=override.club,
        total_score=override.total_score,
        is_override=True,
        override_id=override.id,
        note=override.note,
    )


def list_public_winners(db: Connection) -> list[PublicWinner]:
    """Return standings winners with active administrative overrides applied."""
    winners = fetch_all(
        db,
        PublicWinner,
        "SELECT s.name AS season_name, s.id AS season_id,"
        " 'individual' AS winner_type, i.category, i.athlete_name AS winner_name,"
        " i.club, i.total_score FROM individual_standings i"
        " JOIN seasons s ON s.id = i.season_id WHERE i.position = 1"
        " UNION ALL"
        " SELECT s.name, s.id, 'team', t.category, t.team_name, t.club,"
        " t.total_score FROM team_standings t"
        " JOIN seasons s ON s.id = t.season_id WHERE t.position = 1"
        " ORDER BY season_name DESC, 3, 4, 5",
    )
    for override in list_winner_overrides(db, active_only=True):
        key = (override.season_id, override.winner_type, override.category)
        if override.mode == "replace":
            winners = [
                winner
                for winner in winners
                if (winner.season_id, winner.winner_type, winner.category) != key
            ]
        winners.append(_override_as_winner(override))
    return sorted(
        winners,
        key=lambda winner: (
            winner.season_name,
            winner.winner_type,
            winner.category,
            winner.winner_name,
        ),
        reverse=True,
    )
