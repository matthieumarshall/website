"""Tests for Pydantic models."""

import math
from datetime import datetime

import pytest

from website.models import PaginatedPosts, Post, PostCreate, User, UserRole


class TestUserRole:
    def test_values(self) -> None:
        assert UserRole.admin == "admin"
        assert UserRole.content_creator == "content_creator"

    def test_is_str_enum(self) -> None:
        assert isinstance(UserRole.admin, str)


class TestUserModel:
    def test_valid_user(self) -> None:
        u = User(id=1, username="alice", hashed_password="hash", role=UserRole.admin)
        assert u.username == "alice"
        assert u.role == UserRole.admin

    def test_frozen(self) -> None:
        u = User(id=1, username="alice", hashed_password="hash", role=UserRole.admin)
        with pytest.raises(Exception):
            u.username = "bob"  # verifying frozen model raises

    def test_role_coercion_from_string(self) -> None:
        u = User(id=1, username="x", hashed_password="h", role="admin")  # type: ignore[arg-type]
        assert u.role == UserRole.admin

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(Exception):
            User(id=1, username="x", hashed_password="h", role="superuser")  # type: ignore[arg-type]


class TestPostModel:
    def _make_post(self, **kwargs: object) -> Post:
        now = datetime(2026, 1, 1)
        return Post(
            id=int(kwargs.get("id", 1)),  # type: ignore[arg-type]
            title=str(kwargs.get("title", "Hello")),
            content=str(kwargs.get("content", "<p>World</p>")),
            author_id=int(kwargs.get("author_id", 1)),  # type: ignore[arg-type]
            author_username=str(kwargs.get("author_username", "alice")),
            created_at=kwargs.get("created_at", now),  # type: ignore[arg-type]
            updated_at=kwargs.get("updated_at", now),  # type: ignore[arg-type]
            published=bool(kwargs.get("published", True)),
        )

    def test_valid_post(self) -> None:
        p = self._make_post()
        assert p.title == "Hello"

    def test_frozen(self) -> None:
        p = self._make_post()
        with pytest.raises(Exception):
            p.title = "Changed"


class TestPostCreate:
    def test_valid(self) -> None:
        pc = PostCreate(title="T", content="<p>C</p>")
        assert pc.title == "T"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(Exception):
            PostCreate(title="T")  # type: ignore[call-arg]


class TestPaginatedPosts:
    def _posts(self, n: int) -> list[Post]:
        return [
            Post(
                id=i,
                title=f"Post {i}",
                content="x",
                author_id=1,
                author_username="a",
                created_at=datetime(2026, 1, i + 1),
                updated_at=datetime(2026, 1, i + 1),
                published=True,
            )
            for i in range(1, n + 1)
        ]

    def test_build_total_pages(self) -> None:
        p = PaginatedPosts.build(posts=self._posts(3), page=1, per_page=10, total=25)
        assert p.total_pages == 3

    def test_build_single_page(self) -> None:
        p = PaginatedPosts.build(posts=self._posts(5), page=1, per_page=10, total=5)
        assert p.total_pages == 1

    def test_build_zero_total_gives_one_page(self) -> None:
        p = PaginatedPosts.build(posts=[], page=1, per_page=10, total=0)
        assert p.total_pages == 1

    def test_total_pages_math(self) -> None:
        for total in range(1, 55):
            per_page = 10
            p = PaginatedPosts.build(posts=[], page=1, per_page=per_page, total=total)
            assert p.total_pages == max(1, math.ceil(total / per_page))
