"""Unit tests for migration helpers (_migration_helpers.py).

Tests cover season auto-creation, fixture auto-creation, deduplication checks,
and error handling for the import workflow.
"""

from datetime import date

import duckdb
import pytest

# Import helpers
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(_ROOT))
from _migration_helpers import (  # noqa: E402, type: ignore
    create_fixture_if_missing,
    create_season_if_missing,
    fixture_exists,
    result_exists,
)


@pytest.mark.unit
def test_create_season_if_missing_idempotent(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that create_season_if_missing is idempotent (doesn't duplicate seasons)."""
    season_id_1 = create_season_if_missing(test_db, "2021-2022")
    season_id_2 = create_season_if_missing(test_db, "2021-2022")
    season_id_3 = create_season_if_missing(test_db, "2021-2022")

    # All calls should return the same ID
    assert season_id_1 == season_id_2 == season_id_3

    # Database should only have one season with this name
    result = test_db.execute(
        "SELECT COUNT(*) FROM seasons WHERE name = '2021-2022'"
    ).fetchone()
    assert result is not None
    assert result[0] == 1


@pytest.mark.unit
def test_create_season_if_missing_creates_new_season(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that create_season_if_missing creates a new season if not found."""
    # Verify season doesn't exist
    result = test_db.execute(
        "SELECT COUNT(*) FROM seasons WHERE name = '2020-2021'"
    ).fetchone()
    assert result is not None
    assert result[0] == 0

    # Create season
    season_id = create_season_if_missing(test_db, "2020-2021")

    # Verify it was created
    result = test_db.execute(
        "SELECT id, name FROM seasons WHERE id = ?", [season_id]
    ).fetchone()
    assert result is not None
    assert result[1] == "2020-2021"


@pytest.mark.unit
def test_create_season_if_missing_case_insensitive(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that season lookups are case-insensitive."""
    season_id_1 = create_season_if_missing(test_db, "2021-2022")
    season_id_2 = create_season_if_missing(test_db, "2021-2022")
    season_id_3 = create_season_if_missing(test_db, "2021-2022")

    # All should return the same ID
    assert season_id_1 == season_id_2 == season_id_3


@pytest.mark.unit
def test_create_fixture_if_missing_idempotent(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that create_fixture_if_missing is idempotent."""
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)

    fixture_id_1 = create_fixture_if_missing(
        test_db, season_id, fixture_date, "Bicester Heritage"
    )
    fixture_id_2 = create_fixture_if_missing(
        test_db, season_id, fixture_date, "Bicester Heritage"
    )
    fixture_id_3 = create_fixture_if_missing(
        test_db,
        season_id,
        fixture_date,
        "Different Venue",  # different venue name
    )

    # Dedup by (season_id, date), so all should return same ID
    assert fixture_id_1 == fixture_id_2 == fixture_id_3

    # Database should only have one fixture for this date
    result = test_db.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season_id = ? AND date = ?",
        [season_id, fixture_date],
    ).fetchone()
    assert result is not None
    assert result[0] == 1


@pytest.mark.unit
def test_create_fixture_if_missing_creates_fixture(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that create_fixture_if_missing creates a new fixture."""
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 15)

    fixture_id = create_fixture_if_missing(
        test_db, season_id, fixture_date, "Ascott-under-Wychwood"
    )

    # Verify it was created
    result = test_db.execute(
        "SELECT id, date, title FROM fixtures WHERE id = ?", [fixture_id]
    ).fetchone()
    assert result is not None
    assert result[1] == fixture_date
    # Title should be the venue name passed in
    assert "Ascott" in result[2]


@pytest.mark.unit
def test_fixture_exists_returns_true_for_existing_fixture(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that fixture_exists returns True for existing fixtures."""
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    create_fixture_if_missing(test_db, season_id, fixture_date, "Bicester")

    # Fixture should exist
    assert fixture_exists(test_db, season_id, fixture_date) is True


@pytest.mark.unit
def test_fixture_exists_returns_false_for_missing_fixture(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that fixture_exists returns False for non-existent fixtures."""
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 2, 14)

    # Fixture should not exist
    assert fixture_exists(test_db, season_id, fixture_date) is False


@pytest.mark.unit
def test_result_exists_returns_true_for_existing_result(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that result_exists returns True for existing results."""
    # Create prerequisite data
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Bicester")

    # Create a race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [fixture_id, "Men"],
    ).fetchone()
    race_id = int(result[0])

    # Insert a result
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "John Smith", "25:30", "SM40", "M"],
    )

    # Result should exist
    assert result_exists(test_db, race_id, "John Smith", "25:30") is True


@pytest.mark.unit
def test_result_exists_returns_false_for_missing_result(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that result_exists returns False for non-existent results."""
    # Create prerequisite data
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Bicester")

    # Create a race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [fixture_id, "Men"],
    ).fetchone()
    race_id = int(result[0])

    # Result should not exist
    assert result_exists(test_db, race_id, "Jane Doe", "26:00") is False


@pytest.mark.unit
def test_result_exists_deduplicates_by_athlete_and_time(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that result deduplication considers (race_id, athlete_name, time) tuple."""
    # Create prerequisite data
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Bicester")

    # Create a race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [fixture_id, "Men"],
    ).fetchone()
    race_id = int(result[0])

    # Insert multiple results with same athlete but different times
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "John Smith", "25:30", "SM40", "M"],
    )

    # Same athlete, same time = exists
    assert result_exists(test_db, race_id, "John Smith", "25:30") is True

    # Same athlete, different time = doesn't exist
    assert result_exists(test_db, race_id, "John Smith", "25:31") is False

    # Different athlete, same time = doesn't exist
    assert result_exists(test_db, race_id, "Jane Doe", "25:30") is False


@pytest.mark.integration
def test_full_workflow_create_season_fixture_results(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Integration test: complete workflow of creating season, fixture, and results."""
    # Auto-create season
    season_id = create_season_if_missing(test_db, "2021-2022")
    assert season_id > 0

    # Auto-create fixture
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(
        test_db, season_id, fixture_date, "Bicester Heritage"
    )
    assert fixture_id > 0
    assert fixture_exists(test_db, season_id, fixture_date)

    # Create race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    race_id = int(race[0])

    # Insert results
    for pos, name, time in [
        (1, "John Smith", "25:30"),
        (2, "Jane Doe", "26:00"),
        (3, "Mike Johnson", "26:30"),
    ]:
        test_db.execute(
            "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [race_id, pos, name, time, "SM40", "M"],
        )

    # Verify all results exist
    assert result_exists(test_db, race_id, "John Smith", "25:30")
    assert result_exists(test_db, race_id, "Jane Doe", "26:00")
    assert result_exists(test_db, race_id, "Mike Johnson", "26:30")

    # Verify counts
    result = test_db.execute(
        "SELECT COUNT(*) FROM results WHERE race_id = ?", [race_id]
    ).fetchone()
    assert result is not None
    assert result[0] == 3
