import duckdb
import pytest

from website import repository
from website.database import run_migrations
from website.models import Season
from cli.seed_fixture import _create_fixture


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


@pytest.fixture()
def season(db: duckdb.DuckDBPyConnection) -> Season:
    return repository.create_season(db, name="2025-2026")


class TestCreateFixture:
    def test_creates_and_returns_fixture(
        self, db: duckdb.DuckDBPyConnection, season: Season
    ) -> None:
        fixture = _create_fixture(
            db, "2025-2026", "Round 1", "2025-11-02", "Cirencester Park", "", ""
        )
        assert fixture.title == "Round 1"
        assert fixture.id > 0
        assert fixture.season_id == season.id

    def test_raises_when_season_not_found(self, db: duckdb.DuckDBPyConnection) -> None:
        with pytest.raises(ValueError, match="No season found"):
            _create_fixture(db, "nonexistent", "Round 1", "2025-11-02", "Venue", "", "")

    def test_raises_for_duplicate_title_in_same_season(
        self, db: duckdb.DuckDBPyConnection, season: Season
    ) -> None:
        _create_fixture(db, "2025-2026", "Round 1", "2025-11-02", "Venue A", "", "")
        with pytest.raises(ValueError, match="already exists"):
            _create_fixture(db, "2025-2026", "Round 1", "2025-12-07", "Venue B", "", "")

    def test_duplicate_title_check_is_case_insensitive(
        self, db: duckdb.DuckDBPyConnection, season: Season
    ) -> None:
        _create_fixture(db, "2025-2026", "Round 1", "2025-11-02", "Venue", "", "")
        with pytest.raises(ValueError, match="already exists"):
            _create_fixture(db, "2025-2026", "round 1", "2025-12-07", "Venue", "", "")

    def test_season_name_lookup_is_case_insensitive(
        self, db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_season(db, name="Spring 2025")
        fixture = _create_fixture(
            db, "SPRING 2025", "Round 1", "2025-04-01", "Venue", "", ""
        )
        assert fixture.title == "Round 1"

    def test_stores_address_and_travel_instructions(
        self, db: duckdb.DuckDBPyConnection, season: Season
    ) -> None:
        fixture = _create_fixture(
            db,
            "2025-2026",
            "Round 1",
            "2025-11-02",
            "Venue",
            "123 Test St",
            "Take the M1.",
        )
        assert fixture.address == "123 Test St"
        assert fixture.travel_instructions == "Take the M1."
