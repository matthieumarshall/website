"""Race and result persistence."""

import re

from website.db import Connection
from website.models import Race, Result
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

_RACE_SELECT = (
    "SELECT id, fixture_id, name, display_order, created_at, racetec_url FROM races"
)
_RESULT_SELECT = (
    "SELECT id, race_id, position, race_number, athlete_name, time,"
    " category, category_position, gender, gender_position, club, source,"
    " is_locked, external_key FROM results"
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


def get_result_by_id(db: Connection, result_id: int) -> Result | None:
    """Return one result row."""
    return fetch_one(db, Result, f"{_RESULT_SELECT} WHERE id = ?", [result_id])


def update_race_racetec_url(
    db: Connection, race_id: int, racetec_url: str | None
) -> Race | None:
    """Set a race's individual RaceTec results URL."""
    db.execute(
        "UPDATE races SET racetec_url = ? WHERE id = ?",
        [racetec_url, race_id],
    )
    return get_race_by_id(db, race_id)


def create_race(
    db: Connection, fixture_id: int, name: str, display_order: int = 0
) -> Race:
    """Insert a race and return it."""
    race = fetch_one(
        db,
        Race,
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?) "
        "RETURNING id, fixture_id, name, display_order, created_at, racetec_url",
        [fixture_id, name, display_order],
    )
    return require(race, "race")


def get_race_by_name(db: Connection, fixture_id: int, name: str) -> Race | None:
    """Return the race for *fixture_id* matching *name* (case-insensitive), or None."""
    return fetch_one(
        db,
        Race,
        f"{_RACE_SELECT} WHERE fixture_id = ? AND LOWER(name) = LOWER(?)",
        [fixture_id, name.strip()],
    )


def delete_results_for_race(db: Connection, race_id: int) -> None:
    """Delete all results for *race_id*."""
    db.execute("DELETE FROM results WHERE race_id = ?", [race_id])


def delete_unlocked_imported_results_for_race(db: Connection, race_id: int) -> None:
    """Clear only rows which a future import is allowed to replace."""
    db.execute(
        "DELETE FROM results WHERE race_id = ?"
        " AND source = 'imported' AND is_locked = false",
        [race_id],
    )


def create_results_batch(
    db: Connection,
    rows: list[
        tuple[
            int,
            int,
            int | None,
            str,
            str,
            str,
            int | None,
            str,
            int | None,
            str | None,
        ]
    ],
) -> int:
    """Bulk-insert results rows into the database."""
    if not rows:
        return 0
    db.executemany(
        "INSERT INTO results"
        " (race_id, position, race_number, athlete_name, time, category,"
        " category_position, gender, gender_position, club)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def create_imported_results_batch(
    db: Connection,
    rows: list[
        tuple[
            int,
            int,
            int | None,
            str,
            str,
            str,
            int | None,
            str,
            int | None,
            str | None,
            str,
        ]
    ],
) -> int:
    """Insert synchronised rows with the identity used to protect edits."""
    if not rows:
        return 0
    db.executemany(
        "INSERT INTO results"
        " (race_id, position, race_number, athlete_name, time, category,"
        " category_position, gender, gender_position, club, source, is_locked,"
        " external_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', false, ?)",
        rows,
    )
    return len(rows)


def locked_external_keys_for_race(db: Connection, race_id: int) -> set[str]:
    """Return imported identities that staff have protected from synchronisation."""
    rows = db.execute(
        "SELECT external_key FROM results WHERE race_id = ?"
        " AND is_locked = true AND external_key IS NOT NULL",
        [race_id],
    ).fetchall()
    return {str(key) for (key,) in rows}


def lock_result(db: Connection, result_id: int) -> Result | None:
    """Mark a result as a staff correction protected from imports."""
    db.execute(
        "UPDATE results SET source = 'manual', is_locked = true WHERE id = ?",
        [result_id],
    )
    return fetch_one(db, Result, f"{_RESULT_SELECT} WHERE id = ?", [result_id])


def update_result(  # noqa: PLR0913 — one parameter per result column
    db: Connection,
    result_id: int,
    position: int,
    athlete_name: str,
    time: str,
    category: str,
    gender: str,
    race_number: int | None = None,
    category_position: int | None = None,
    gender_position: int | None = None,
    club: str | None = None,
) -> Result | None:
    """Save a staff correction and protect it from future imports."""
    db.execute(
        "UPDATE results SET position = ?, race_number = ?, athlete_name = ?,"
        " time = ?, category = ?, category_position = ?, gender = ?,"
        " gender_position = ?, club = ?, source = 'manual', is_locked = true"
        " WHERE id = ?",
        [
            position,
            race_number,
            athlete_name,
            time,
            category,
            category_position,
            gender,
            gender_position,
            club,
            result_id,
        ],
    )
    return get_result_by_id(db, result_id)


def delete_result(db: Connection, result_id: int) -> None:
    """Delete one result row."""
    db.execute("DELETE FROM results WHERE id = ?", [result_id])


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
