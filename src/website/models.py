import math
from datetime import date, datetime
from enum import Enum

from fastapi_permissions import Allow
from pydantic import BaseModel, ConfigDict, field_validator


class UserRole(str, Enum):
    admin = "admin"
    content_creator = "content_creator"


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
# Static Pages
# ---------------------------------------------------------------------------


class StaticPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    content: str
    updated_at: datetime
    updated_by_id: int | None
