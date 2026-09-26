"""Seasons, fixtures and fixture images."""

import json
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

MAX_FIXTURES_PER_SEASON = 5


class TimetableEntry(BaseModel):
    """One row of a fixture's race timetable."""

    model_config = ConfigDict(frozen=True)

    event: str
    time: str


def parse_timetable_json(timetable_json: str) -> list[TimetableEntry]:
    """Deserialise timetable JSON from a form hidden-input field.

    Expects a JSON array of ``{"event": str, "time": str}`` objects.
    Invalid input yields an empty list; blank or malformed rows are dropped.
    """
    try:
        raw = json.loads(timetable_json or "[]")
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []
    entries: list[TimetableEntry] = []
    for item in raw:
        if isinstance(item, dict):
            event = str(item.get("event", "")).strip()
            time = str(item.get("time", "")).strip()
            if event or time:
                entries.append(TimetableEntry(event=event, time=time))
    return entries


class Season(BaseModel):
    """A league season."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    created_at: datetime


class SeasonCreate(BaseModel):
    """Validated input for creating a season."""

    name: str


class Fixture(BaseModel):
    """A single fixture (race day) within a season."""

    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    title: str
    date: date
    location_name: str
    address: str
    timetable: list[TimetableEntry]
    travel_instructions: str
    created_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    what3words: str | None = None
    # Path relative to data/uploads/ of the original results PDF, populated by
    # the migration script.  None when no source document is available.
    source_pdf: str | None = None

    @field_validator("timetable", mode="before")
    @classmethod
    def _parse_timetable_json(cls, v: object) -> object:
        """Accept the timetable as stored in the database (a JSON string)."""
        if v is None:
            return []
        if isinstance(v, str):
            return json.loads(v or "[]")
        return v


class FixtureImage(BaseModel):
    """An uploaded course map or photo for a fixture."""

    model_config = ConfigDict(frozen=True)

    id: int
    fixture_id: int
    filename: str
    uploaded_at: datetime


class FixtureCreate(BaseModel):
    """Validated fixture details used for create, update and copy."""

    title: str
    date: date
    location_name: str
    address: str
    timetable: list[TimetableEntry]
    travel_instructions: str
    what3words_word1: str = ""
    what3words_word2: str = ""
    what3words_word3: str = ""

    @field_validator(
        "what3words_word1", "what3words_word2", "what3words_word3", mode="before"
    )
    @classmethod
    def validate_what3words_word(cls, v: object) -> str:
        """Validate what3words word: lowercase, alphabetic only, stripped."""
        if not isinstance(v, str):
            return ""
        v = v.strip().lower()
        if v and not all(c.isalpha() for c in v):
            raise ValueError("What3Words words must contain only letters")
        return v

    @property
    def what3words_words(self) -> tuple[str, str, str]:
        """Return the three what3words words in order."""
        return (self.what3words_word1, self.what3words_word2, self.what3words_word3)


class FixtureUpdate(FixtureCreate):
    """Validated input for updating an existing fixture."""
