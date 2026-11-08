"""Season standings rows and categories."""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ScoreValue = int | float | str
StandingsType = Literal["individual", "team"]


class _StandingBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    category: str
    position: int
    club: str | None
    total_score: int
    rounds_competed: int
    fixture_scores: str
    is_imported: bool
    updated_at: datetime | None = None
    # Per-fixture scores keyed by fixture id, filled in by the standings service.
    scores_by_fixture: dict[str, ScoreValue] = {}


class IndividualStanding(_StandingBase):
    """An athlete's position in an individual standings category."""

    athlete_name: str


class TeamStanding(_StandingBase):
    """A team's position in a team standings category."""

    team_name: str
    team_label: str | None
    division: int | None = None
    division_position: int | None = None


class CalculatedIndividualStanding(BaseModel):
    """A freshly calculated individual standings row, ready to be stored."""

    model_config = ConfigDict(frozen=True)

    category: str
    position: int
    athlete_name: str
    club: str | None
    total_score: int
    rounds_competed: int
    fixture_scores: dict[str, int]


class CalculatedTeamStanding(BaseModel):
    """A freshly calculated team standings row, ready to be stored."""

    model_config = ConfigDict(frozen=True)

    category: str
    position: int
    team_name: str
    club: str | None
    team_label: str | None
    total_score: int
    rounds_competed: int
    fixture_scores: dict[str, int]


class _TeamRoundResultData(BaseModel):
    model_config = ConfigDict(frozen=True)

    fixture_id: int
    category: str
    position: int
    team_name: str
    club: str | None
    team_label: str | None
    score: int
    scoring_members: list[str]
    division: int | None = None
    division_position: int | None = None

    @field_validator("scoring_members", mode="before")
    @classmethod
    def parse_scoring_members(cls, value: object) -> object:
        """Decode the JSON representation stored by DuckDB."""
        return json.loads(value) if isinstance(value, str) else value


class TeamRoundResult(_TeamRoundResultData):
    """A team's calculated result and scoring runners for one fixture."""

    id: int


class CalculatedTeamRoundResult(_TeamRoundResultData):
    """A freshly calculated team result, ready to be stored."""


class StandingCategory(BaseModel):
    """A category that has standings rows for a season."""

    model_config = ConfigDict(frozen=True)

    category: str
    type: StandingsType
    count: int
