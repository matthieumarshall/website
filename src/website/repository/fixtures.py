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
    " tempo_results_url, auto_sync_enabled, auto_sync_until,"
    " auto_sync_interval_minutes, last_synced_at, last_sync_attempt_at,"
    " sync_status, sync_error, round_number"
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
    return fixture.model_copy(update={"timetable": schedule or fixture.timetable})


def replace_timetable_items(
    db: Connection, fixture_id: int, timetable: list[TimetableEntry]
) -> list[TimetableEntry]:
    """Replace a round schedule and mirror it to the legacy JSON column."""
    db.execute("DELETE FROM timetable_items WHERE fixture_id = ?", [fixture_id])
    if timetable:
        db.executemany(
            "INSERT INTO timetable_items"
            " (fixture_id, race_id, time, event, display_order)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (fixture_id, entry.race_id, entry.time, entry.event, index)
                for index, entry in enumerate(timetable)
            ],
        )
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
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY round_number ASC, date ASC",
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
    tempo_results_url: str | None = None,
) -> Fixture:
    """Insert a fixture and return it.

    Raises:
        ValueError: If the season already has the maximum number of fixtures.
    """
    current_count = count_fixtures_for_season(db, season_id)
    if current_count >= MAX_FIXTURES_PER_SEASON:
        raise ValueError(
            f"Season {season_id} already has {current_count} fixtures "
            f"(maximum is {MAX_FIXTURES_PER_SEASON})."
        )
    round_number = current_count + 1
    db.execute(
        "INSERT INTO fixtures"
        " (season_id, title, date, location_name, address, timetable,"
        " travel_instructions, latitude, longitude, what3words, tempo_results_url,"
        " round_number)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            tempo_results_url,
            round_number,
        ],
    )
    fixture = fetch_one(
        db,
        Fixture,
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY created_at DESC LIMIT 1",
        [season_id],
    )
    created = require(fixture, "fixture")
    replace_timetable_items(db, created.id, timetable)
    return require(get_fixture_by_id(db, created.id), "fixture")


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
    tempo_results_url: str | None = None,
) -> Fixture | None:
    """Update a fixture and return it, or None if it does not exist."""
    db.execute(
        "UPDATE fixtures SET title = ?, date = ?, location_name = ?, address = ?,"
        " timetable = ?, travel_instructions = ?, latitude = ?, longitude = ?,"
        " what3words = ?, tempo_results_url = ? WHERE id = ?",
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
            tempo_results_url,
            fixture_id,
        ],
    )
    if get_fixture_by_id(db, fixture_id) is None:
        return None
    replace_timetable_items(db, fixture_id, timetable)
    return get_fixture_by_id(db, fixture_id)


def update_fixture_sync_settings(
    db: Connection,
    fixture_id: int,
    tempo_results_url: str | None,
    auto_sync_enabled: bool,
    auto_sync_until: dt.datetime | None,
    auto_sync_interval_minutes: int = 15,
) -> Fixture | None:
    """Update external sync configuration for a fixture."""
    db.execute(
        "UPDATE fixtures SET tempo_results_url = ?, auto_sync_enabled = ?,"
        " auto_sync_until = ?, auto_sync_interval_minutes = ? WHERE id = ?",
        [
            tempo_results_url,
            auto_sync_enabled,
            auto_sync_until,
            auto_sync_interval_minutes,
            fixture_id,
        ],
    )
    return get_fixture_by_id(db, fixture_id)


def update_fixture_sync_status(
    db: Connection,
    fixture_id: int,
    sync_status: str,
    sync_error: str | None = None,
    last_synced_at: dt.datetime | None = None,
    last_sync_attempt_at: dt.datetime | None = None,
) -> Fixture | None:
    """Update status and optional attempt/success timestamps for a fixture."""
    db.execute(
        "UPDATE fixtures SET sync_status = ?, sync_error = ?,"
        " last_synced_at = COALESCE(?, last_synced_at),"
        " last_sync_attempt_at = COALESCE(?, last_sync_attempt_at) WHERE id = ?",
        [sync_status, sync_error, last_synced_at, last_sync_attempt_at, fixture_id],
    )
    return get_fixture_by_id(db, fixture_id)


def list_fixtures_needing_sync(db: Connection) -> list[Fixture]:
    """Return fixtures with active auto-sync and at least one configured URL."""
    return fetch_all(
        db,
        Fixture,
        f"{_FIXTURE_SELECT} WHERE auto_sync_enabled = true"  # nosec B608 — fixed SQL fragments
        " AND (tempo_results_url IS NOT NULL OR EXISTS ("
        " SELECT 1 FROM races WHERE races.fixture_id = fixtures.id"
        " AND races.racetec_url IS NOT NULL))",
        [],
    )


def delete_fixture(db: Connection, fixture_id: int) -> bool:
    """Delete a round and all relational children in dependency order."""
    race_rows = db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchall()
    for (race_id,) in race_rows:
        db.execute("DELETE FROM results WHERE race_id = ?", [race_id])
    db.execute("DELETE FROM timetable_items WHERE fixture_id = ?", [fixture_id])
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
