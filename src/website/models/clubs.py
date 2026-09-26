"""Member clubs and club manager accounts."""

from pydantic import BaseModel, ConfigDict


class Club(BaseModel):
    """A member club."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    oxl_code: str
    ea_club_id: str
    is_active: bool
    opentrack_code: str | None = None
    website_url: str | None = None
    is_oxfordshire_member: bool = True


class ClubManager(BaseModel):
    """The club a club-manager user is responsible for."""

    model_config = ConfigDict(frozen=True)

    id: int
    user_id: int
    club_id: int
    is_active: bool
    club_name: str


class ClubManagerListing(BaseModel):
    """A club manager row for the admin list."""

    model_config = ConfigDict(frozen=True)

    manager_id: int
    user_id: int
    club_id: int
    is_active: bool
    club_name: str
    username: str
    email: str | None
