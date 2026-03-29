"""Tests for database connection factory and migration runner."""

import duckdb
import pytest

from website.database import get_db, run_migrations


class TestGetDb:
    def test_yields_connection(self) -> None:
        # Use the in-memory path so we don't touch data/
        import os

        os.environ["DATABASE_URL"] = ":memory:"
        try:
            gen2 = get_db()
            con = next(gen2)
            assert isinstance(con, duckdb.DuckDBPyConnection)
            try:
                next(gen2)
            except StopIteration:
                pass
        finally:
            del os.environ["DATABASE_URL"]

    def test_connection_closes_after_use(self) -> None:
        import os

        os.environ["DATABASE_URL"] = ":memory:"
        try:
            gen = get_db()
            con = next(gen)
            try:
                next(gen)
            except StopIteration:
                pass
            # After generator exhausted, executing should raise
            with pytest.raises(Exception):
                con.execute("SELECT 1")
        finally:
            del os.environ["DATABASE_URL"]


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
