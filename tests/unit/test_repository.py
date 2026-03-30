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


# ---------------------------------------------------------------------------
# Season repository
# ---------------------------------------------------------------------------


class TestCreateSeason:
    def test_creates_season_with_correct_name(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(db, "2025-2026")
        assert season.name == "2025-2026"
        assert season.id > 0

    def test_ids_increment(self, db: duckdb.DuckDBPyConnection) -> None:
        s1 = repository.create_season(db, "2024-2025")
        s2 = repository.create_season(db, "2025-2026")
        assert s2.id > s1.id

    def test_duplicate_name_raises(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_season(db, "2025-2026")
        with pytest.raises(Exception):
            repository.create_season(db, "2025-2026")


class TestListSeasons:
    def test_empty_returns_empty_list(self, db: duckdb.DuckDBPyConnection) -> None:
        assert repository.list_seasons(db) == []

    def test_returns_all_seasons(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_season(db, "2024-2025")
        repository.create_season(db, "2025-2026")
        seasons = repository.list_seasons(db)
        assert len(seasons) == 2

    def test_ordered_by_name_descending(self, db: duckdb.DuckDBPyConnection) -> None:
        repository.create_season(db, "2023-2024")
        repository.create_season(db, "2025-2026")
        repository.create_season(db, "2024-2025")
        seasons = repository.list_seasons(db)
        assert seasons[0].name == "2025-2026"
        assert seasons[-1].name == "2023-2024"


class TestGetSeasonById:
    def test_returns_none_for_unknown_id(self, db: duckdb.DuckDBPyConnection) -> None:
        assert repository.get_season_by_id(db, 9999) is None

    def test_returns_season_for_valid_id(self, db: duckdb.DuckDBPyConnection) -> None:
        created = repository.create_season(db, "2025-2026")
        fetched = repository.get_season_by_id(db, created.id)
        assert fetched is not None
        assert fetched.name == "2025-2026"


class TestDeleteSeason:
    def test_deletes_empty_season(self, db: duckdb.DuckDBPyConnection) -> None:
        season = repository.create_season(db, "2025-2026")
        result = repository.delete_season(db, season.id)
        assert result is True
        assert repository.get_season_by_id(db, season.id) is None

    def test_raises_if_fixtures_exist(self, db: duckdb.DuckDBPyConnection) -> None:
        season = repository.create_season(db, "2025-2026")
        repository.create_fixture(
            db,
            season_id=season.id,
            title="Round 1",
            date="2025-09-01",
            location_name="Venue",
            address="1 Main St",
            timetable=[],
            travel_instructions="",
        )
        with pytest.raises(ValueError, match="fixture"):
            repository.delete_season(db, season.id)


# ---------------------------------------------------------------------------
# Fixture repository
# ---------------------------------------------------------------------------


def _make_season(db: duckdb.DuckDBPyConnection, name: str = "2025-2026"):  # type: ignore[return]
    return repository.create_season(db, name)


class TestCreateFixture:
    def test_creates_fixture_with_correct_fields(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        from website.models import TimetableEntry

        season = _make_season(db)
        entry = TimetableEntry(event="Registration", time="09:00")
        fixture = repository.create_fixture(
            db,
            season_id=season.id,
            title="Round 1",
            date="2025-09-01",
            location_name="Town Hall",
            address="1 Main St",
            timetable=[entry],
            travel_instructions="Take the bus.",
        )
        assert fixture.title == "Round 1"
        assert str(fixture.date) == "2025-09-01"
        assert fixture.location_name == "Town Hall"
        assert fixture.address == "1 Main St"
        assert len(fixture.timetable) == 1
        assert fixture.timetable[0].event == "Registration"
        assert fixture.travel_instructions == "Take the bus."

    def test_fixture_id_positive(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        fixture = repository.create_fixture(
            db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        assert fixture.id > 0

    def test_raises_when_cap_exceeded(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        for i in range(5):
            repository.create_fixture(
                db, season.id, f"Round {i + 1}", f"2025-0{i + 1}-01", "V", "A", [], ""
            )
        with pytest.raises(ValueError, match="maximum"):
            repository.create_fixture(
                db, season.id, "Round 6", "2025-07-01", "V", "A", [], ""
            )

    def test_cap_applies_per_season(self, db: duckdb.DuckDBPyConnection) -> None:
        """Cap is per-season: filling one season does not block another."""
        s1 = repository.create_season(db, "2024-2025")
        s2 = repository.create_season(db, "2025-2026")
        for i in range(5):
            repository.create_fixture(
                db, s1.id, f"Round {i + 1}", f"2025-0{i + 1}-01", "V", "A", [], ""
            )
        # Should not raise for the second season
        fixture = repository.create_fixture(
            db, s2.id, "Round 1", "2025-09-01", "V", "A", [], ""
        )
        assert fixture.id > 0


class TestListFixturesForSeason:
    def test_returns_empty_for_no_fixtures(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        assert repository.list_fixtures_for_season(db, season.id) == []

    def test_returns_only_fixtures_for_season(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        s1 = repository.create_season(db, "2024-2025")
        s2 = repository.create_season(db, "2025-2026")
        repository.create_fixture(db, s1.id, "R1", "2024-09-01", "V", "A", [], "")
        repository.create_fixture(db, s2.id, "R1", "2025-09-01", "V", "A", [], "")
        assert len(repository.list_fixtures_for_season(db, s1.id)) == 1
        assert len(repository.list_fixtures_for_season(db, s2.id)) == 1

    def test_ordered_by_date_ascending(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        repository.create_fixture(db, season.id, "R3", "2025-11-01", "V", "A", [], "")
        repository.create_fixture(db, season.id, "R1", "2025-09-01", "V", "A", [], "")
        repository.create_fixture(db, season.id, "R2", "2025-10-01", "V", "A", [], "")
        fixtures = repository.list_fixtures_for_season(db, season.id)
        assert fixtures[0].title == "R1"
        assert fixtures[1].title == "R2"
        assert fixtures[2].title == "R3"


class TestGetFixtureById:
    def test_returns_none_for_unknown_id(self, db: duckdb.DuckDBPyConnection) -> None:
        assert repository.get_fixture_by_id(db, 9999) is None

    def test_returns_fixture_for_valid_id(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        created = repository.create_fixture(
            db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        fetched = repository.get_fixture_by_id(db, created.id)
        assert fetched is not None
        assert fetched.title == "R1"


class TestUpdateFixture:
    def test_updates_fields(self, db: duckdb.DuckDBPyConnection) -> None:
        from website.models import TimetableEntry

        season = _make_season(db)
        fixture = repository.create_fixture(
            db, season.id, "Old", "2025-09-01", "OldVenue", "OldAddr", [], ""
        )
        entry = TimetableEntry(event="Start", time="10:00")
        updated = repository.update_fixture(
            db,
            fixture.id,
            title="New",
            date="2025-10-01",
            location_name="NewVenue",
            address="NewAddr",
            timetable=[entry],
            travel_instructions="Drive.",
        )
        assert updated is not None
        assert updated.title == "New"
        assert updated.location_name == "NewVenue"
        assert len(updated.timetable) == 1
        assert updated.travel_instructions == "Drive."

    def test_returns_none_for_missing_fixture(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        result = repository.update_fixture(
            db, 9999, "T", "2025-09-01", "V", "A", [], ""
        )
        assert result is None


class TestDeleteFixture:
    def test_deletes_fixture(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        fixture = repository.create_fixture(
            db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        repository.delete_fixture(db, fixture.id)
        assert repository.get_fixture_by_id(db, fixture.id) is None

    def test_returns_true(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        fixture = repository.create_fixture(
            db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        assert repository.delete_fixture(db, fixture.id) is True


class TestCountFixturesForSeason:
    def test_returns_zero_for_empty_season(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        assert repository.count_fixtures_for_season(db, season.id) == 0

    def test_increments_on_create(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _make_season(db)
        repository.create_fixture(db, season.id, "R1", "2025-09-01", "V", "A", [], "")
        assert repository.count_fixtures_for_season(db, season.id) == 1
