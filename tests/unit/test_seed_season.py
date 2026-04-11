import duckdb
import pytest

from website.database import run_migrations
from cli.seed_season import _create_season


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


class TestCreateSeason:
    def test_creates_and_returns_season(self, db: duckdb.DuckDBPyConnection) -> None:
        season = _create_season(db, "2025-2026")
        assert season.name == "2025-2026"
        assert season.id > 0

    def test_raises_for_duplicate_name(self, db: duckdb.DuckDBPyConnection) -> None:
        _create_season(db, "2025-2026")
        with pytest.raises(ValueError, match="already exists"):
            _create_season(db, "2025-2026")

    def test_duplicate_check_is_case_insensitive(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        _create_season(db, "Spring 2025")
        with pytest.raises(ValueError, match="already exists"):
            _create_season(db, "spring 2025")

    def test_multiple_distinct_seasons_allowed(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        s1 = _create_season(db, "2024-2025")
        s2 = _create_season(db, "2025-2026")
        assert s1.id != s2.id
