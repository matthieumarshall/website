"""Fixture and fixture image persistence."""

import datetime as dt
import json

from website.db import Connection
from website.models import (
    MAX_FIXTURES_PER_SEASON,
    Fixture,
    FixtureImage,
    TimetableEntry,
)
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

_FIXTURE_SELECT = (
    "SELECT id, season_id, title, date, location_name, address, timetable,"
    " travel_instructions, created_at, latitude, longitude, what3words, source_pdf,"
    " round_number"
    " FROM fixtures"
)
_IMAGE_SELECT = "SELECT id, fixture_id, filename, uploaded_at FROM fixture_images"
_TIMETABLE_SELECT = (
    "SELECT id, race_id, time, event, display_order FROM timetable_items"
)


def _timetable_json(timetable: list[TimetableEntry]) -> str:
    return json.dumps([entry.model_dump() for entry in timetable])


def list_timetable_items(db: Connection, fixture_id: int) -> list[TimetableEntry]:
    """Return a round schedule in its staff-defined order."""
    return fetch_all(
        db,
        TimetableEntry,
        f"{_TIMETABLE_SELECT} WHERE fixture_id = ? ORDER BY display_order, id",
        [fixture_id],
    )


def _with_schedule(db: Connection, fixture: Fixture | None) -> Fixture | None:
    """Prefer the linked schedule, preserving legacy JSON until it is edited."""
    if fixture is None:
        return None
    schedule = list_timetable_items(db, fixture.id)
    return fixture.model_copy(update={"timetable": schedule})


def validate_timetable_races(
    db: Connection, fixture_id: int, timetable: list[TimetableEntry]
) -> None:
    """Ensure that every linked race belongs to the selected round."""
    for entry in timetable:
        if entry.race_id is not None:
            owner = db.execute(
                "SELECT fixture_id FROM races WHERE id = ?", [entry.race_id]
            ).fetchone()
            if owner is None or owner[0] != fixture_id:
                raise ValueError("A timetable race must belong to this round.")


def replace_timetable_items(
    db: Connection, fixture_id: int, timetable: list[TimetableEntry]
) -> list[TimetableEntry]:
    """Replace a round schedule and mirror it to the legacy JSON column."""
    validate_timetable_races(db, fixture_id, timetable)
    existing = {entry.id for entry in list_timetable_items(db, fixture_id)}
    retained: set[int] = set()
    for index, entry in enumerate(timetable):
        if entry.id is not None and entry.id in existing:
            if entry.id in retained:
                raise ValueError("Duplicate timetable item.")
            retained.add(entry.id)
            db.execute(
                "UPDATE timetable_items SET race_id = ?, time = ?, event = ?, "
                "display_order = ? WHERE id = ?",
                [entry.race_id, entry.time, entry.event, index, entry.id],
            )
        else:
            db.execute(
                "INSERT INTO timetable_items "
                "(fixture_id, race_id, time, event, display_order) "
                "VALUES (?, ?, ?, ?, ?)",
                [fixture_id, entry.race_id, entry.time, entry.event, index],
            )
    for item_id in existing - retained:
        db.execute("DELETE FROM timetable_items WHERE id = ?", [item_id])
    db.execute(
        "UPDATE fixtures SET timetable = ? WHERE id = ?",
        [_timetable_json(timetable), fixture_id],
    )
    return list_timetable_items(db, fixture_id)


def link_matching_timetable_race(
    db: Connection, fixture_id: int, race_id: int, race_name: str
) -> None:
    """Link matching schedule labels to a newly-created race."""
    db.execute(
        "UPDATE timetable_items SET race_id = ?"
        " WHERE fixture_id = ? AND race_id IS NULL"
        " AND LOWER(TRIM(event)) = LOWER(TRIM(?))",
        [race_id, fixture_id, race_name],
    )


def count_fixtures_for_season(db: Connection, season_id: int) -> int:
    """Return how many fixtures a season has."""
    return fetch_count(
        db, "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    )


def list_fixtures_for_season(db: Connection, season_id: int) -> list[Fixture]:
    """Return a season's rounds in their stable order."""
    fixtures = fetch_all(
        db,
        Fixture,
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY date ASC, round_number ASC",
        [season_id],
    )
    return [
        resolved for fixture in fixtures if (resolved := _with_schedule(db, fixture))
    ]


def list_fixture_dates(db: Connection, season_id: int) -> list[dt.date]:
    """Return the dates of every fixture in a season."""
    rows = db.execute(
        "SELECT date FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchall()
    return [row[0] for row in rows]


def get_fixture_by_id(db: Connection, fixture_id: int) -> Fixture | None:
    """Return the fixture with *fixture_id*, or None."""
    return _with_schedule(
        db, fetch_one(db, Fixture, f"{_FIXTURE_SELECT} WHERE id = ?", [fixture_id])
    )


def create_fixture(  # noqa: PLR0913 — one parameter per fixture column
    db: Connection,
    season_id: int,
    title: str,
    date: str | dt.date,
    location_name: str,
    address: str,
    timetable: list[TimetableEntry],
    travel_instructions: str,
    latitude: float | None = None,
    longitude: float | None = None,
    what3words: str | None = None,
) -> Fixture:
    """Insert a fixture and return it.

    Raises:
        ValueError: If the season already has the maximum number of fixtures.
    """
    if any(entry.race_id is not None for entry in timetable):
        raise ValueError("A new round cannot link a race from another round.")
    current_count = count_fixtures_for_season(db, season_id)
    if current_count >= MAX_FIXTURES_PER_SEASON:
        raise ValueError(
            f"Season {season_id} already has {current_count} fixtures "
            f"(maximum is {MAX_FIXTURES_PER_SEASON})."
        )
    row = db.execute(
        "SELECT COALESCE(MAX(round_number), 0) + 1 FROM fixtures WHERE season_id = ?",
        [season_id],
    ).fetchone()
    if row is None:
        raise RuntimeError("Could not allocate a round number")
    round_number = row[0]
    inserted = db.execute(
        "INSERT INTO fixtures"
        " (season_id, title, date, location_name, address, timetable,"
        " travel_instructions, latitude, longitude, what3words, round_number)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [
            season_id,
            title,
            date,
            location_name,
            address,
            _timetable_json(timetable),
            travel_instructions,
            latitude,
            longitude,
            what3words,
            round_number,
        ],
    )
    if inserted is None:
        raise RuntimeError("Could not create round")
    created_id = inserted.fetchone()
    if created_id is None:
        raise RuntimeError("Could not create round")
    replace_timetable_items(db, created_id[0], timetable)
    return require(get_fixture_by_id(db, created_id[0]), "fixture")


def update_fixture(  # noqa: PLR0913 — one parameter per fixture column
    db: Connection,
    fixture_id: int,
    title: str,
    date: str | dt.date,
    location_name: str,
    address: str,
    timetable: list[TimetableEntry],
    travel_instructions: str,
    latitude: float | None = None,
    longitude: float | None = None,
    what3words: str | None = None,
) -> Fixture | None:
    """Update a fixture and return it, or None if it does not exist."""
    validate_timetable_races(db, fixture_id, timetable)
    db.execute(
        "UPDATE fixtures SET title = ?, date = ?, location_name = ?, address = ?,"
        " timetable = ?, travel_instructions = ?, latitude = ?, longitude = ?,"
        " what3words = ? WHERE id = ?",
        [
            title,
            date,
            location_name,
            address,
            _timetable_json(timetable),
            travel_instructions,
            latitude,
            longitude,
            what3words,
            fixture_id,
        ],
    )
    if get_fixture_by_id(db, fixture_id) is None:
        return None
    replace_timetable_items(db, fixture_id, timetable)
    return get_fixture_by_id(db, fixture_id)


def delete_fixture(db: Connection, fixture_id: int) -> bool:
    """Delete a round and all relational children in dependency order."""
    race_rows = db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchall()
    for (race_id,) in race_rows:
        db.execute("DELETE FROM results WHERE race_id = ?", [race_id])
    db.execute("DELETE FROM timetable_items WHERE fixture_id = ?", [fixture_id])
    db.execute("DELETE FROM team_round_results WHERE fixture_id = ?", [fixture_id])
    db.execute("DELETE FROM races WHERE fixture_id = ?", [fixture_id])
    db.execute("DELETE FROM fixture_documents WHERE fixture_id = ?", [fixture_id])
    db.execute("DELETE FROM fixture_images WHERE fixture_id = ?", [fixture_id])
    db.execute("DELETE FROM fixtures WHERE id = ?", [fixture_id])
    return True


def set_fixture_source_pdf(
    db: Connection, fixture_id: int, source_pdf: str | None
) -> None:
    """Store the path (relative to ``data/uploads``) of a fixture's results PDF.

    Pass ``None`` to clear the field.
    """
    db.execute(
        "UPDATE fixtures SET source_pdf = ? WHERE id = ?",
        [source_pdf, fixture_id],
    )


def list_fixture_images(db: Connection, fixture_id: int) -> list[FixtureImage]:
    """Return a fixture's images, oldest first."""
    return fetch_all(
        db,
        FixtureImage,
        f"{_IMAGE_SELECT} WHERE fixture_id = ? ORDER BY uploaded_at ASC",
        [fixture_id],
    )


def get_fixture_image_by_id(db: Connection, image_id: int) -> FixtureImage | None:
    """Return the fixture image with *image_id*, or None."""
    return fetch_one(db, FixtureImage, f"{_IMAGE_SELECT} WHERE id = ?", [image_id])


def create_fixture_image(
    db: Connection, fixture_id: int, filename: str
) -> FixtureImage:
    """Record an uploaded image for a fixture and return it."""
    db.execute(
        "INSERT INTO fixture_images (fixture_id, filename) VALUES (?, ?)",
        [fixture_id, filename],
    )
    image = fetch_one(
        db,
        FixtureImage,
        f"{_IMAGE_SELECT} WHERE fixture_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        [fixture_id],
    )
    return require(image, "fixture image")


def delete_fixture_image(db: Connection, image_id: int) -> str | None:
    """Delete a fixture image record, returning its filename (None if absent)."""
    image = get_fixture_image_by_id(db, image_id)
    if image is None:
        return None
    db.execute("DELETE FROM fixture_images WHERE id = ?", [image_id])
    return image.filename
