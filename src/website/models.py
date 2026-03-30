import math
from datetime import date, datetime
from enum import Enum

from fastapi_permissions import Allow
from pydantic import BaseModel, ConfigDict


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


class FixtureCreate(BaseModel):
    title: str
    date: date
    location_name: str
    address: str
    timetable: list[TimetableEntry]
    travel_instructions: str


class FixtureUpdate(BaseModel):
    title: str
    date: date
    location_name: str
    address: str
    timetable: list[TimetableEntry]
    travel_instructions: str
