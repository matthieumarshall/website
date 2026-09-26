"""Race and result persistence."""

import re

from website.db import Connection
from website.models import Race, Result
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

_RACE_SELECT = "SELECT id, fixture_id, name, display_order, created_at FROM races"
_RESULT_SELECT = (
    "SELECT id, race_id, position, race_number, athlete_name, time,"
    " category, category_position, gender, gender_position, club FROM results"
)
_AGE_GROUP = re.compile(r"\bU(\d+)\b", re.IGNORECASE)


def race_sort_key(name: str) -> tuple[int, int, str]:
    """Sort key: junior races (U9, U11, …) ordered by age first, then alpha."""
    match = _AGE_GROUP.search(name)
    if match:
        return (0, int(match.group(1)), name.lower())
    return (1, 0, name.lower())


def list_races_for_fixture(db: Connection, fixture_id: int) -> list[Race]:
    """Return a fixture's races, juniors by age group first."""
    races = fetch_all(db, Race, f"{_RACE_SELECT} WHERE fixture_id = ?", [fixture_id])
    return sorted(races, key=lambda race: race_sort_key(race.name))


def get_race_by_id(db: Connection, race_id: int) -> Race | None:
    """Return the race with *race_id*, or None."""
    return fetch_one(db, Race, f"{_RACE_SELECT} WHERE id = ?", [race_id])


def create_race(
    db: Connection, fixture_id: int, name: str, display_order: int = 0
) -> Race:
    """Insert a race and return it."""
    db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, name, display_order],
    )
    race = fetch_one(
        db,
        Race,
        f"{_RACE_SELECT} WHERE fixture_id = ? ORDER BY created_at DESC LIMIT 1",
        [fixture_id],
    )
    return require(race, "race")


def list_results_for_race(db: Connection, race_id: int) -> list[Result]:
    """Return a race's results in finishing order."""
    return fetch_all(
        db,
        Result,
        f"{_RESULT_SELECT} WHERE race_id = ? ORDER BY position ASC",
        [race_id],
    )


def fixture_has_results(db: Connection, fixture_id: int) -> bool:
    """Return True if any race in the fixture has results."""
    count = fetch_count(
        db,
        "SELECT COUNT(*) FROM results r"
        " JOIN races rc ON rc.id = r.race_id"
        " WHERE rc.fixture_id = ?",
        [fixture_id],
    )
    return count > 0


def create_result(  # noqa: PLR0913 — one parameter per result column
    db: Connection,
    race_id: int,
    position: int,
    athlete_name: str,
    time: str,
    category: str,
    gender: str,
    race_number: int | None = None,
    category_position: int | None = None,
    gender_position: int | None = None,
    club: str | None = None,
) -> Result:
    """Insert a result and return it."""
    db.execute(
        "INSERT INTO results"
        " (race_id, position, race_number, athlete_name, time, category,"
        " category_position, gender, gender_position, club)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            race_id,
            position,
            race_number,
            athlete_name,
            time,
            category,
            category_position,
            gender,
            gender_position,
            club,
        ],
    )
    result = fetch_one(
        db,
        Result,
        f"{_RESULT_SELECT} WHERE race_id = ? ORDER BY id DESC LIMIT 1",
        [race_id],
    )
    return require(result, "result")
