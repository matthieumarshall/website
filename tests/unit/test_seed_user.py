import duckdb
import pytest

from website.database import run_migrations
from website.models import UserRole
from cli.seed_user import _add_user


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


class TestAddUser:
    def test_creates_and_returns_user(self, db: duckdb.DuckDBPyConnection) -> None:
        user = _add_user(db, "alice", "password123", UserRole.admin)
        assert user.username == "alice"
        assert user.role == UserRole.admin
        assert user.id > 0

    def test_hashes_password(self, db: duckdb.DuckDBPyConnection) -> None:
        user = _add_user(db, "alice", "password123", UserRole.admin)
        assert user.hashed_password != "password123"

    def test_content_creator_role(self, db: duckdb.DuckDBPyConnection) -> None:
        user = _add_user(db, "bob", "pw", UserRole.content_creator)
        assert user.role == UserRole.content_creator

    def test_raises_for_duplicate_username(self, db: duckdb.DuckDBPyConnection) -> None:
        _add_user(db, "alice", "password123", UserRole.admin)
        with pytest.raises(ValueError, match="already exists"):
            _add_user(db, "alice", "other", UserRole.content_creator)

    def test_duplicate_check_is_case_sensitive(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        _add_user(db, "Alice", "pw", UserRole.admin)
        # "alice" differs from "Alice" — must succeed
        user = _add_user(db, "alice", "pw", UserRole.admin)
        assert user.username == "alice"
