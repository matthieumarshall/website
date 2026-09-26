"""Standings persistence (both calculated and imported rows)."""

import json

from website.db import Connection
from website.models import (
    CalculatedIndividualStanding,
    CalculatedTeamStanding,
    IndividualStanding,
    StandingCategory,
    TeamStanding,
)
from website.repository._rows import fetch_all, fetch_count

_INDIVIDUAL_SELECT = (
    "SELECT id, season_id, category, position, athlete_name, club,"
    " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
    " FROM individual_standings"
)
_TEAM_SELECT = (
    "SELECT id, season_id, category, position, team_name, club, team_label,"
    " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
    " FROM team_standings"
)


def load_individual_standings(
    db: Connection, season_id: int, category: str | None = None
) -> list[IndividualStanding]:
    """Return a season's individual standings, optionally for one category."""
    if category is not None:
        return fetch_all(
            db,
            IndividualStanding,
            f"{_INDIVIDUAL_SELECT} WHERE season_id = ? AND category = ?"  # noqa: S608
            " ORDER BY position ASC",
            [season_id, category],
        )
    return fetch_all(
        db,
        IndividualStanding,
        f"{_INDIVIDUAL_SELECT} WHERE season_id = ?"  # noqa: S608
        " ORDER BY category ASC, position ASC",
        [season_id],
    )


def load_team_standings(
    db: Connection, season_id: int, category: str | None = None
) -> list[TeamStanding]:
    """Return a season's team standings, optionally for one category."""
    if category is not None:
        return fetch_all(
            db,
            TeamStanding,
            f"{_TEAM_SELECT} WHERE season_id = ? AND category = ?"  # noqa: S608
            " ORDER BY position ASC",
            [season_id, category],
        )
    return fetch_all(
        db,
        TeamStanding,
        f"{_TEAM_SELECT} WHERE season_id = ?"  # noqa: S608
        " ORDER BY category ASC, position ASC",
        [season_id],
    )


def list_standing_categories(db: Connection, season_id: int) -> list[StandingCategory]:
    """Return the categories that have standings for a season."""
    return fetch_all(
        db,
        StandingCategory,
        "SELECT category, 'individual' AS type, COUNT(*) AS count"
        " FROM individual_standings WHERE season_id = ? GROUP BY category"
        " UNION ALL"
        " SELECT category, 'team' AS type, COUNT(*) AS count"
        " FROM team_standings WHERE season_id = ? GROUP BY category"
        " ORDER BY type ASC, category ASC",
        [season_id, season_id],
    )


def season_has_standings(db: Connection, season_id: int) -> bool:
    """Return True if any standings rows (calculated or imported) exist."""
    for table in ("individual_standings", "team_standings"):
        count = fetch_count(
            db,
            f"SELECT COUNT(*) FROM {table} WHERE season_id = ?",  # noqa: S608  # nosec B608 — table name from a constant tuple
            [season_id],
        )
        if count > 0:
            return True
    return False


def replace_calculated_individual_standings(
    db: Connection, season_id: int, rows: list[CalculatedIndividualStanding]
) -> None:
    """Replace a season's calculated individual rows, keeping imported rows."""
    db.execute(
        "DELETE FROM individual_standings WHERE season_id = ? AND is_imported = false",
        [season_id],
    )
    if not rows:
        return
    db.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, false)",
        [
            [
                season_id,
                row.category,
                row.position,
                row.athlete_name,
                row.club,
                row.total_score,
                row.rounds_competed,
                json.dumps(row.fixture_scores),
            ]
            for row in rows
        ],
    )


def replace_calculated_team_standings(
    db: Connection, season_id: int, rows: list[CalculatedTeamStanding]
) -> None:
    """Replace a season's calculated team rows, keeping imported rows."""
    db.execute(
        "DELETE FROM team_standings WHERE season_id = ? AND is_imported = false",
        [season_id],
    )
    if not rows:
        return
    db.executemany(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, false)",
        [
            [
                season_id,
                row.category,
                row.position,
                row.team_name,
                row.club,
                row.team_label,
                row.total_score,
                row.rounds_competed,
                json.dumps(row.fixture_scores),
            ]
            for row in rows
        ],
    )
