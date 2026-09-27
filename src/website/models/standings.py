"""Season standings rows and categories."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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


class StandingCategory(BaseModel):
    """A category that has standings rows for a season."""

    model_config = ConfigDict(frozen=True)

    category: str
    type: StandingsType
    count: int
