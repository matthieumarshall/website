"""Club identities and their relationships to senior team divisions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from website.models.clubs import Club

Gender = Literal["men", "women"]
DivisionNumber = Literal[1, 2, 3]


class ClubAlias(BaseModel):
    """A result name explicitly linked to a member club."""

    model_config = ConfigDict(frozen=True)

    id: int
    club_id: int
    name: str


class Division(BaseModel):
    """One gender's division in a particular season."""

    model_config = ConfigDict(frozen=True)

    season_id: int
    gender: Gender
    number: DivisionNumber


class Team(BaseModel):
    """A club's team in a competition category."""

    model_config = ConfigDict(frozen=True)

    club: Club
    category: str
    label: str | None
    division: Division | None = None
