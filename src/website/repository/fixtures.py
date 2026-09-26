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
    " travel_instructions, created_at, latitude, longitude, what3words, source_pdf"
    " FROM fixtures"
)
_IMAGE_SELECT = "SELECT id, fixture_id, filename, uploaded_at FROM fixture_images"


def _timetable_json(timetable: list[TimetableEntry]) -> str:
    return json.dumps([entry.model_dump() for entry in timetable])


def count_fixtures_for_season(db: Connection, season_id: int) -> int:
    """Return how many fixtures a season has."""
    return fetch_count(
        db, "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    )


def list_fixtures_for_season(db: Connection, season_id: int) -> list[Fixture]:
    """Return a season's fixtures in date order."""
    return fetch_all(
        db,
        Fixture,
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY date ASC",
        [season_id],
    )


def list_fixture_dates(db: Connection, season_id: int) -> list[dt.date]:
    """Return the dates of every fixture in a season."""
    rows = db.execute(
        "SELECT date FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchall()
    return [row[0] for row in rows]


def get_fixture_by_id(db: Connection, fixture_id: int) -> Fixture | None:
    """Return the fixture with *fixture_id*, or None."""
    return fetch_one(db, Fixture, f"{_FIXTURE_SELECT} WHERE id = ?", [fixture_id])


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
    current_count = count_fixtures_for_season(db, season_id)
    if current_count >= MAX_FIXTURES_PER_SEASON:
        raise ValueError(
            f"Season {season_id} already has {current_count} fixtures "
            f"(maximum is {MAX_FIXTURES_PER_SEASON})."
        )
    db.execute(
        "INSERT INTO fixtures"
        " (season_id, title, date, location_name, address, timetable,"
        " travel_instructions, latitude, longitude, what3words)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        ],
    )
    fixture = fetch_one(
        db,
        Fixture,
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY created_at DESC LIMIT 1",
        [season_id],
    )
    return require(fixture, "fixture")


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
    return get_fixture_by_id(db, fixture_id)


def delete_fixture(db: Connection, fixture_id: int) -> bool:
    """Delete a fixture."""
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
