"""Races and individual race results."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Race(BaseModel):
    """A race (for example, "U13 Girls") within a fixture."""

    model_config = ConfigDict(frozen=True)

    id: int
    fixture_id: int
    name: str
    display_order: int
    created_at: datetime


class Result(BaseModel):
    """One finisher's result in a race."""

    model_config = ConfigDict(frozen=True)

    id: int
    race_id: int
    position: int
    race_number: int | None
    athlete_name: str
    time: str
    category: str
    category_position: int | None
    gender: str
    gender_position: int | None
    club: str | None


class RaceWithResults(BaseModel):
    """A race together with its ordered results."""

    model_config = ConfigDict(frozen=True)

    race: Race
    results: list[Result]
