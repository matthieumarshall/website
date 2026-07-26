import math
from datetime import date, datetime
from enum import Enum

from fastapi_permissions import Allow
from pydantic import BaseModel, ConfigDict, field_validator


class UserRole(str, Enum):
    admin = "admin"
    content_creator = "content_creator"
    club_manager = "club_manager"


class User(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    hashed_password: str
    role: UserRole


class Post(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    content: str
    author_id: int
    author_username: str
    created_at: datetime
    updated_at: datetime
    published: bool


class PostCreate(BaseModel):
    title: str
    content: str


class PostResource:
    """Wraps a Post and provides an ACL for fastapi-permissions."""

    def __init__(self, post: "Post") -> None:
        self.post = post

    def __acl__(self) -> list[tuple]:
        return [
            (Allow, f"user:{self.post.author_id}", ("edit", "delete")),
            (Allow, "role:admin", ("edit", "delete")),
        ]


class PaginatedPosts(BaseModel):
    model_config = ConfigDict(frozen=True)

    posts: list[Post]
    page: int
    per_page: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        posts: list[Post],
        page: int,
        per_page: int,
        total: int,
    ) -> "PaginatedPosts":
        return cls(
            posts=posts,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        )


# ---------------------------------------------------------------------------
# Seasons & Fixtures
# ---------------------------------------------------------------------------

_MAX_FIXTURES_PER_SEASON = 5


class TimetableEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: str
    time: str


class Season(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    created_at: datetime


class SeasonCreate(BaseModel):
    name: str


class Fixture(BaseModel):
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
    # Relative path from data/original_website/files/results/ to the source PDF,
    # populated by the migration script.  None when no source document is available.
    source_pdf: str | None = None


class FixtureImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    fixture_id: int
    filename: str
    uploaded_at: datetime


class FixtureCreate(BaseModel):
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
    def validate_what3words_word(cls, v: str) -> str:
        """Validate what3words word: lowercase, alphanumeric only, stripped."""
        if not isinstance(v, str):
            return ""
        v = v.strip().lower()
        # Allow only lowercase letters; what3words words contain only letters
        if v and not all(c.isalpha() for c in v):
            raise ValueError("What3Words words must contain only letters")
        return v


class FixtureUpdate(BaseModel):
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
    def validate_what3words_word(cls, v: str) -> str:
        """Validate what3words word: lowercase, alphanumeric only, stripped."""
        if not isinstance(v, str):
            return ""
        v = v.strip().lower()
        # Allow only lowercase letters; what3words words contain only letters
        if v and not all(c.isalpha() for c in v):
            raise ValueError("What3Words words must contain only letters")
        return v


# ---------------------------------------------------------------------------
# Races & Results
# ---------------------------------------------------------------------------


class Race(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    fixture_id: int
    name: str
    display_order: int
    created_at: datetime


class Result(BaseModel):
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
    model_config = ConfigDict(frozen=True)

    race: Race
    results: list[Result]


# ---------------------------------------------------------------------------
# Administration documents
# ---------------------------------------------------------------------------


class AdministrationDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    section_id: int
    display_name: str
    filename: str
    href: (
        str  # computed by repository: /uploads/administration/<section_slug>/<filename>
    )
    file_type: str
    sort_order: int


class AdministrationSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    slug: str  # used for HTML anchors and URL path segments
    title: str
    description: str
    sort_order: int
    documents: list[AdministrationDocument]


# ---------------------------------------------------------------------------
# Static Pages
# ---------------------------------------------------------------------------


class StaticPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    content: str
    updated_at: datetime
    updated_by_id: int | None


# ---------------------------------------------------------------------------
# Team Entries
# ---------------------------------------------------------------------------


class Club(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    oxl_code: str
    ea_club_id: str
    is_active: bool
    opentrack_code: str | None = None
    website_url: str | None = None
    is_oxfordshire_member: bool = True


class ExternalLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    url: str
    category: str
    description: str | None
    sort_order: int
    is_active: bool


class DivisionAssignment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    season_name: str
    club_id: int
    club_name: str
    gender: str
    division: int


class WinnerOverride(BaseModel):
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


class ClubManager(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    user_id: int
    club_id: int
    is_active: bool
    club_name: str


class AthleteEntryRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    ea_urn: int
    athlete_name: str
    date_of_birth: date
    ea_age_category: str
    is_junior: bool
    amount_pence: int
    race_number: int | None = None


class EntryBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    club_id: int
    manager_user_id: int
    status: str
    fixtures_remaining_at_entry: int
    total_pence: int
    stripe_checkout_session_id: str | None
    stripe_payment_intent_id: str | None
    stripe_payment_method: str | None
    paid_at: datetime | None
    created_at: datetime
