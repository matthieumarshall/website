import duckdb
import pytest

from website import repository
from website.auth import hash_password
from website.database import run_migrations
from website.models import PaginatedPosts, Post, User, UserRole


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


@pytest.fixture()
def admin_user(db: duckdb.DuckDBPyConnection) -> User:
    return repository.create_user(
        db, "admin", hash_password("password"), UserRole.admin
    )


@pytest.fixture()
def creator_user(db: duckdb.DuckDBPyConnection) -> User:
    return repository.create_user(
        db, "creator", hash_password("password"), UserRole.content_creator
    )


# ---------------------------------------------------------------------------
# User repository
# ---------------------------------------------------------------------------


class TestGetUserByUsername:
    def test_returns_none_for_unknown_user(self, db: duckdb.DuckDBPyConnection) -> None:
        assert repository.get_user_by_username(db, "nobody") is None

    def test_returns_user_after_creation(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_user(db, "alice", hash_password("pw"), UserRole.admin)
        user = repository.get_user_by_username(db, "alice")
        assert user is not None
        assert user.username == "alice"
        assert user.role == UserRole.admin

    def test_username_is_case_sensitive(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_user(
            db, "Alice", hash_password("pw"), UserRole.content_creator
        )
        assert repository.get_user_by_username(db, "alice") is None


class TestCreateUser:
    def test_creates_user_with_correct_fields(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        user = repository.create_user(
            db, "bob", hash_password("secret"), UserRole.content_creator
        )
        assert isinstance(user, User)
        assert user.username == "bob"
        assert user.role == UserRole.content_creator
        assert user.id > 0

    def test_ids_increment(self, db: duckdb.DuckDBPyConnection) -> None:
        u1 = repository.create_user(db, "u1", hash_password("pw"), UserRole.admin)
        u2 = repository.create_user(db, "u2", hash_password("pw"), UserRole.admin)
        assert u2.id > u1.id

    def test_duplicate_username_raises(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_user(db, "dup", hash_password("pw"), UserRole.admin)
        with pytest.raises(Exception):
            repository.create_user(db, "dup", hash_password("pw2"), UserRole.admin)


# ---------------------------------------------------------------------------
# Post repository
# ---------------------------------------------------------------------------


class TestCreatePost:
    def test_returns_post_with_correct_fields(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        post = repository.create_post(db, "Hello", "<p>World</p>", admin_user.id)
        assert isinstance(post, Post)
        assert post.title == "Hello"
        assert post.content == "<p>World</p>"
        assert post.author_id == admin_user.id
        assert post.author_username == "admin"
        assert post.published is True

    def test_post_id_is_positive(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        post = repository.create_post(db, "T", "<p>C</p>", admin_user.id)
        assert post.id > 0


class TestGetPostById:
    def test_returns_none_for_missing_post(self, db: duckdb.DuckDBPyConnection) -> None:
        assert repository.get_post_by_id(db, 9999) is None

    def test_returns_post_for_valid_id(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        created = repository.create_post(db, "T", "<p>C</p>", admin_user.id)
        fetched = repository.get_post_by_id(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "T"


class TestUpdatePost:
    def test_updates_title_and_content(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        post = repository.create_post(db, "Old", "<p>old</p>", admin_user.id)
        updated = repository.update_post(db, post.id, "New", "<p>new</p>")
        assert updated is not None
        assert updated.title == "New"
        assert updated.content == "<p>new</p>"

    def test_returns_none_for_missing_post(self, db: duckdb.DuckDBPyConnection) -> None:
        result = repository.update_post(db, 9999, "T", "<p>C</p>")
        assert result is None


class TestDeletePost:
    def test_delete_removes_post(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        post = repository.create_post(db, "T", "<p>C</p>", admin_user.id)
        repository.delete_post(db, post.id)
        assert repository.get_post_by_id(db, post.id) is None

    def test_delete_returns_true(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        post = repository.create_post(db, "T", "<p>C</p>", admin_user.id)
        assert repository.delete_post(db, post.id) is True


class TestListPosts:
    def _make_posts(
        self, db: duckdb.DuckDBPyConnection, author_id: int, count: int
    ) -> None:
        for i in range(count):
            repository.create_post(db, f"Post {i}", f"<p>{i}</p>", author_id)

    def test_returns_paginated_posts_type(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        result = repository.list_posts(db)
        assert isinstance(result, PaginatedPosts)

    def test_empty_database_returns_zero_total(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        result = repository.list_posts(db)
        assert result.total == 0
        assert result.posts == []
        assert result.total_pages == 1  # max(1, ceil(0/10))

    def test_page_1_returns_first_ten(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 15)
        result = repository.list_posts(db, page=1, per_page=10)
        assert len(result.posts) == 10
        assert result.total == 15
        assert result.total_pages == 2

    def test_page_2_returns_remaining_posts(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 15)
        result = repository.list_posts(db, page=2, per_page=10)
        assert len(result.posts) == 5

    def test_out_of_range_page_returns_empty_list(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 5)
        result = repository.list_posts(db, page=999, per_page=10)
        assert result.posts == []
        assert result.total == 5

    def test_pagination_metadata_is_correct(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 25)
        result = repository.list_posts(db, page=3, per_page=10)
        assert result.page == 3
        assert result.per_page == 10
        assert result.total == 25
        assert result.total_pages == 3
        assert len(result.posts) == 5

    def test_exact_page_boundary(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 20)
        result = repository.list_posts(db, page=2, per_page=10)
        assert len(result.posts) == 10
        assert result.total_pages == 2

    def test_published_only_filter(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        self._make_posts(db, admin_user.id, 3)
        # Unpublish one post
        post = repository.list_posts(db, published_only=False).posts[0]
        db.execute("UPDATE posts SET published = false WHERE id = ?", [post.id])

        published = repository.list_posts(db, published_only=True)
        all_posts = repository.list_posts(db, published_only=False)
        assert published.total == 2
        assert all_posts.total == 3

    def test_posts_ordered_newest_first(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        for i in range(3):
            repository.create_post(db, f"Post {i}", "<p>x</p>", admin_user.id)
        result = repository.list_posts(db)
        titles = [p.title for p in result.posts]
        # Newest first — "Post 2" was created last
        assert titles[0] == "Post 2"
        assert titles[-1] == "Post 0"

    def test_author_username_populated(
        self, db: duckdb.DuckDBPyConnection, admin_user: User
    ) -> None:
        repository.create_post(db, "T", "<p>C</p>", admin_user.id)
        result = repository.list_posts(db)
        assert result.posts[0].author_username == "admin"
