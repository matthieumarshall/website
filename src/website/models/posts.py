"""News posts."""

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Post(BaseModel):
    """A published or draft news post."""

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
    """Validated input for creating or editing a post."""

    title: str
    content: str


class PaginatedPosts(BaseModel):
    """One page of posts plus pagination metadata."""

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
        """Construct a page, deriving ``total_pages`` (always at least 1)."""
        return cls(
            posts=posts,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        )
