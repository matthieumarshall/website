"""Public content managed by staff: external links, divisions and winners."""

from pydantic import BaseModel, ConfigDict


class ExternalLink(BaseModel):
    """A curated link to an external website."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    url: str
    category: str
    description: str | None
    sort_order: int
    is_active: bool


class DivisionAssignment(BaseModel):
    """A club placed in a division for a season and gender."""

    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    season_name: str
    club_id: int
    club_name: str
    gender: str
    division: int


class DivisionMember(BaseModel):
    """A club as displayed inside a division table."""

    model_config = ConfigDict(frozen=True)

    assignment_id: int
    club_id: int
    name: str
    website_url: str | None


class WinnerOverride(BaseModel):
    """An administrative correction or addition to the published winners."""

    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    season_name: str
    winner_type: str
    category: str
    winner_name: str
    club: str | None
    total_score: int | None
    note: str | None
    mode: str
    is_active: bool
    updated_by_id: int | None


class PublicWinner(BaseModel):
    """A category winner as shown on the public Past Winners page."""

    model_config = ConfigDict(frozen=True)

    season_name: str
    season_id: int
    winner_type: str
    category: str
    winner_name: str
    club: str | None
    total_score: int | None
    is_override: bool = False
    override_id: int | None = None
    note: str | None = None
