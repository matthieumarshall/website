import duckdb
import pytest

from website import repository
from website.database import run_migrations
from website.models import Fixture, Season
from cli.seed_results import _import_results

_VALID_CSV = (
    "position,athlete_name,time,category,gender\n"
    "1,Alice Smith,25:30,Senior,F\n"
    "2,Bob Jones,26:00,Senior,M\n"
)


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


@pytest.fixture()
def season(db: duckdb.DuckDBPyConnection) -> Season:
    return repository.create_season(db, name="2025-2026")


@pytest.fixture()
def fixture(db: duckdb.DuckDBPyConnection, season: Season) -> Fixture:
    return repository.create_fixture(
        db,
        season_id=season.id,
        title="Round 1",
        date="2025-11-02",
        location_name="Venue",
        address="",
        timetable=[],
        travel_instructions="",
    )


class TestImportResults:
    def test_imports_valid_csv(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(_VALID_CSV, encoding="utf-8")
        inserted, fixture_id = _import_results(
            db, "2025-2026", "Round 1", "Senior", csv_file
        )
        assert inserted == 2
        assert fixture_id == fixture.id

    def test_raises_when_csv_not_found(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        with pytest.raises(ValueError, match="CSV file not found"):
            _import_results(
                db,
                "2025-2026",
                "Round 1",
                "Senior",
                tmp_path / "missing.csv",  # type: ignore[operator]
            )

    def test_raises_when_season_not_found(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(_VALID_CSV, encoding="utf-8")
        with pytest.raises(ValueError, match="No season found"):
            _import_results(db, "nonexistent", "Round 1", "Senior", csv_file)

    def test_raises_when_fixture_not_found(
        self,
        db: duckdb.DuckDBPyConnection,
        season: Season,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(_VALID_CSV, encoding="utf-8")
        with pytest.raises(ValueError, match="No fixture found"):
            _import_results(db, "2025-2026", "nonexistent", "Senior", csv_file)

    def test_raises_for_duplicate_race_name(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(_VALID_CSV, encoding="utf-8")
        _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)
        with pytest.raises(ValueError, match="already exists"):
            _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)

    def test_raises_for_missing_required_columns(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        # Missing time, category, gender
        csv_file.write_text("position,athlete_name\n1,Alice\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required columns"):
            _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)

    def test_raises_when_no_data_rows(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(
            "position,athlete_name,time,category,gender\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="no data rows"):
            _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)

    def test_raises_on_row_parse_error(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        # "cat pos" maps to category_position; "notanumber" causes int() to fail
        csv_content = (
            "position,athlete_name,time,category,gender,cat pos\n"
            "1,Alice,25:30,Senior,F,notanumber\n"
        )
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(csv_content, encoding="utf-8")
        with pytest.raises(ValueError, match="CSV row"):
            _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)

    def test_transaction_rolls_back_on_row_error(
        self,
        db: duckdb.DuckDBPyConnection,
        fixture: Fixture,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        csv_content = (
            "position,athlete_name,time,category,gender,cat pos\n"
            "1,Alice,25:30,Senior,F,\n"
            "2,Bob,26:00,Senior,M,notanumber\n"
        )
        csv_file = tmp_path / "results.csv"  # type: ignore[operator]
        csv_file.write_text(csv_content, encoding="utf-8")
        with pytest.raises(ValueError, match="CSV row"):
            _import_results(db, "2025-2026", "Round 1", "Senior", csv_file)
        # No race should have been committed
        races = repository.list_races_for_fixture(db, fixture.id)
        assert races == []
