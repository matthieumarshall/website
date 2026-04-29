"""Tests for database connection factory and migration runner."""

import types

import duckdb
import pytest

from website.database import _get_db_path, get_db, run_migrations


def _make_request_with_db(con: duckdb.DuckDBPyConnection) -> object:
    """Build a minimal mock Request whose app.state.db is *con*."""
    state = types.SimpleNamespace(db=con)
    app = types.SimpleNamespace(state=state)
    return types.SimpleNamespace(app=app)


class TestGetDb:
    def test_yields_connection(self) -> None:
        con = duckdb.connect(":memory:")
        run_migrations(con)
        request = _make_request_with_db(con)
        try:
            gen = get_db(request)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
            cursor = next(gen)
            assert isinstance(cursor, duckdb.DuckDBPyConnection)
            try:
                next(gen)
            except StopIteration:
                pass
        finally:
            con.close()

    def test_connection_closes_after_use(self) -> None:
        con = duckdb.connect(":memory:")
        run_migrations(con)
        request = _make_request_with_db(con)
        try:
            gen = get_db(request)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
            cursor = next(gen)
            try:
                next(gen)
            except StopIteration:
                pass
            # After generator exhausted the cursor should be closed
            with pytest.raises(Exception):
                cursor.execute("SELECT 1")
        finally:
            con.close()


class TestRunMigrations:
    def test_creates_migrations_table(self, test_db: duckdb.DuckDBPyConnection) -> None:
        # run_migrations already called in fixture; table should exist
        result = test_db.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_name = '_migrations'"
        ).fetchone()
        assert result is not None

    def test_creates_users_table(self, test_db: duckdb.DuckDBPyConnection) -> None:
        result = test_db.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_name = 'users'"
        ).fetchone()
        assert result is not None

    def test_creates_posts_table(self, test_db: duckdb.DuckDBPyConnection) -> None:
        result = test_db.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_name = 'posts'"
        ).fetchone()
        assert result is not None

    def test_idempotent(self, test_db: duckdb.DuckDBPyConnection) -> None:
        """Running migrations twice should not raise."""
        run_migrations(test_db)

    def test_records_applied_migrations(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        rows = test_db.execute("SELECT filename FROM _migrations").fetchall()
        filenames = {r[0] for r in rows}
        assert "0001_create_users.sql" in filenames
        assert "0002_create_posts.sql" in filenames

    def test_can_insert_and_query_user(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        test_db.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
            ["db_test_user", "hash", "admin"],
        )
        row = test_db.execute(
            "SELECT username, role FROM users WHERE username = ?", ["db_test_user"]
        ).fetchone()
        assert row is not None
        assert row[0] == "db_test_user"
        assert row[1] == "admin"


class TestGetDbPath:
    def test_returns_database_url_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "custom/path.duckdb")
        assert _get_db_path() == "custom/path.duckdb"

    def test_returns_default_path_when_env_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        result = _get_db_path()
        assert "app.duckdb" in result
