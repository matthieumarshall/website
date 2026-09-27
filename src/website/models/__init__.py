"""Pydantic data models for every domain of the website.

Models are grouped by domain in submodules and re-exported here so callers
can simply ``from website.models import Fixture``.
"""

from website.models.administration import (
    AdministrationDocument,
    AdministrationSection,
    DeletedDocument,
    StaticPage,
)
from website.models.clubs import Club, ClubManager, ClubManagerListing
from website.models.entries import (
    PAID_STATUSES,
    PAYABLE_STATUSES,
    AthleteChoice,
    AthleteEntryListing,
    AthleteEntryRow,
    ClubAllocationRow,
    EAAthlete,
    EntryBatch,
    EntryBatchSummary,
    PaidAthleteEntry,
    SeasonEntryConfig,
)
from website.models.fixtures import (
    MAX_FIXTURES_PER_SEASON,
    Fixture,
    FixtureCreate,
    FixtureImage,
    FixtureUpdate,
    Season,
    SeasonCreate,
    TimetableEntry,
)
from website.models.posts import PaginatedPosts, Post, PostCreate
from website.models.public_content import (
    DivisionAssignment,
    DivisionMember,
    ExternalLink,
    PublicWinner,
    WinnerOverride,
)
from website.models.results import Race, RaceWithResults, Result
from website.models.standings import (
    CalculatedIndividualStanding,
    CalculatedTeamStanding,
    IndividualStanding,
    StandingCategory,
    StandingsType,
    TeamStanding,
)
from website.models.users import STAFF_ROLES, CurrentUser, User, UserRole

__all__ = [
    "MAX_FIXTURES_PER_SEASON",
    "PAID_STATUSES",
    "PAYABLE_STATUSES",
    "STAFF_ROLES",
    "AdministrationDocument",
    "AdministrationSection",
    "AthleteChoice",
    "AthleteEntryListing",
    "AthleteEntryRow",
    "CalculatedIndividualStanding",
    "CalculatedTeamStanding",
    "Club",
    "ClubAllocationRow",
    "ClubManager",
    "ClubManagerListing",
    "CurrentUser",
    "DeletedDocument",
    "DivisionAssignment",
    "DivisionMember",
    "EAAthlete",
    "EntryBatch",
    "EntryBatchSummary",
    "ExternalLink",
    "Fixture",
    "FixtureCreate",
    "FixtureImage",
    "FixtureUpdate",
    "IndividualStanding",
    "PaginatedPosts",
    "PaidAthleteEntry",
    "Post",
    "PostCreate",
    "PublicWinner",
    "Race",
    "RaceWithResults",
    "Result",
    "Season",
    "SeasonCreate",
    "SeasonEntryConfig",
    "StandingCategory",
    "StandingsType",
    "StaticPage",
    "TeamStanding",
    "TimetableEntry",
    "User",
    "UserRole",
    "WinnerOverride",
]
