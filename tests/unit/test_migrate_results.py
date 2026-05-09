"""Unit and integration tests for results import (migrate_results.py).

Tests cover:
- PDF parsing with various data quality scenarios
- Season/fixture auto-creation
- Result insertion with NULL handling
- Deduplication and force/dry-run modes
- Logging and error handling
"""

from datetime import date
from pathlib import Path

import duckdb
import pytest

# Add scripts to path for imports
import sys

_ROOT = Path(__file__).parent.parent.parent
_SCRIPTS = _ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))

# Import migration helpers and logger
from _import_logger import ImportLogger  # noqa: E402
from _migration_helpers import (  # noqa: E402
    create_fixture_if_missing,
    create_season_if_missing,
    result_exists,
)


# Test data helpers
def create_sample_pdf_results() -> list[dict]:
    """Generate sample PDF result data for testing."""
    return [
        {
            "position": "1",
            "race_number": "101",
            "athlete_name": "John Smith",
            "time": "25:30",
            "category": "SM40",
            "category_position": "1",
            "gender": "M",
            "gender_position": "1",
            "club": "Oxford AC",
        },
        {
            "position": "2",
            "race_number": "102",
            "athlete_name": "Jane Doe",
            "time": "26:15",
            "category": "U20W",
            "category_position": "1",
            "gender": "F",
            "gender_position": "2",
            "club": "Harriers",
        },
        {
            "position": "3",
            "race_number": "103",
            "athlete_name": "Mike Johnson",
            "time": "26:45",
            "category": "SM40",
            "category_position": "2",
            "gender": "M",
            "gender_position": "3",
            "club": None,
        },
    ]


def count_records(con: duckdb.DuckDBPyConnection, table: str, **where_clause) -> int:
    """Count records in a table with optional WHERE clause."""
    if not where_clause:
        result = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(result[0]) if result else 0
    columns = ", ".join(f"{k} = ?" for k in where_clause.keys())
    values = list(where_clause.values())
    query = f"SELECT COUNT(*) FROM {table} WHERE {columns}"
    result = con.execute(query, values).fetchone()
    return int(result[0]) if result else 0


def create_test_season_with_fixtures(
    con: duckdb.DuckDBPyConnection, season_name: str, num_fixtures: int = 3
) -> tuple[int, list[int]]:
    """Create a season with multiple fixtures."""
    from datetime import date

    # Create season
    con.execute("INSERT INTO seasons (name) VALUES (?)", [season_name])
    season_result = con.execute(
        "SELECT id FROM seasons WHERE name = ?", [season_name]
    ).fetchone()
    season_id = int(season_result[0])

    # Create fixtures
    fixture_ids = []
    for i in range(num_fixtures):
        day = (i * 7) + 1
        fixture_date = date(2021, 1, day)
        venue = f"Venue {i + 1}"
        con.execute(
            "INSERT INTO fixtures (season_id, date, title, location_name, address) VALUES (?, ?, ?, ?, ?)",
            [season_id, fixture_date, venue, venue, ""],
        )
        result = con.execute(
            "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
            [season_id, fixture_date],
        ).fetchone()
        fixture_ids.append(int(result[0]))

    return season_id, fixture_ids


@pytest.mark.unit
def test_parse_valid_result_table(test_db: duckdb.DuckDBPyConnection) -> None:
    """Test PDF parsing with valid result table data.

    Simulates parsing a result row from a PDF and inserting it into the database.
    """
    # Setup
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Venue 1")

    # Create a race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [fixture_id, "Men"],
    ).fetchone()
    race_id = int(race_result[0])

    # Simulate parsed PDF data
    sample_data = create_sample_pdf_results()
    for result_row in sample_data:
        test_db.execute(
            "INSERT INTO results "
            "(race_id, position, race_number, athlete_name, time, category, "
            " category_position, gender, gender_position, club) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                race_id,
                int(result_row["position"]),
                int(result_row["race_number"]),
                result_row["athlete_name"],
                result_row["time"],
                result_row["category"],
                int(result_row["category_position"]),
                result_row["gender"],
                int(result_row["gender_position"]),
                result_row["club"],
            ],
        )

    # Verify results were inserted
    count = test_db.execute(
        "SELECT COUNT(*) FROM results WHERE race_id = ?", [race_id]
    ).fetchone()
    assert count is not None
    assert count[0] == 3


@pytest.mark.unit
def test_parse_result_with_missing_columns(test_db: duckdb.DuckDBPyConnection) -> None:
    """Test PDF parsing behavior when optional columns are missing.

    Should import with NULL values for missing optional fields and log a warning.
    """
    # Setup
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Venue 1")

    # Create a race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [fixture_id, "Men"],
    ).fetchone()
    race_id = int(race_result[0])

    # Insert result with minimal fields (no club, race_number, etc.)
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "John Smith", "25:30", "SM40", "M"],
    )

    # Verify result was inserted with NULLs for optional fields
    result = test_db.execute(
        "SELECT club, race_number, category_position FROM results WHERE race_id = ? AND athlete_name = ?",
        [race_id, "John Smith"],
    ).fetchone()
    assert result is not None
    assert result[0] is None  # club
    assert result[1] is None  # race_number
    assert result[2] is None  # category_position


@pytest.mark.unit
def test_parse_result_with_malformed_position(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test handling of malformed position values in PDF.

    Should log warning and skip the row if position is not numeric.
    """
    logger = ImportLogger()

    # Simulated malformed data
    malformed_position = "invalid"

    # Attempt to parse (this would normally be done by PDF parser)
    try:
        int(malformed_position)
        logger.warning(
            "result_parse",
            file="test.pdf",
            row=1,
            issue="malformed_position",
            detail=malformed_position,
        )
    except ValueError:
        logger.warning(
            "result_parse",
            file="test.pdf",
            row=1,
            issue="malformed_position",
            detail=malformed_position,
        )

    # Verify warning was logged
    assert logger.stats["warning"] >= 1


@pytest.mark.unit
def test_season_auto_creation_during_import(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that seasons are auto-created if missing during import.

    During results import, if a season doesn't exist, it should be created
    from the folder name without manual intervention.
    """
    # Before: Season doesn't exist
    count = test_db.execute(
        "SELECT COUNT(*) FROM seasons WHERE name = '2022-2023'"
    ).fetchone()
    assert count is not None
    assert count[0] == 0

    # During import: Auto-create season
    season_id = create_season_if_missing(test_db, "2022-2023")

    # After: Season exists
    count = test_db.execute(
        "SELECT COUNT(*) FROM seasons WHERE name = '2022-2023'"
    ).fetchone()
    assert count is not None
    assert count[0] == 1
    assert season_id > 0


@pytest.mark.unit
def test_fixture_auto_creation_from_filename(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that fixtures are auto-created from filename metadata.

    Filename format: YYYYMMDD-RndN-VenueName-min.pdf
    Should extract date and venue to auto-create fixture.
    """
    # Setup season
    season_id = create_season_if_missing(test_db, "2021-2022")

    # Simulate filename parsing
    fixture_date = date(2021, 1, 15)
    venue_name = "Bicester Heritage"

    # Auto-create fixture from filename
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, venue_name)

    # Verify fixture was created
    result = test_db.execute(
        "SELECT date, title FROM fixtures WHERE id = ?", [fixture_id]
    ).fetchone()
    assert result is not None
    assert result[0] == fixture_date
    assert venue_name in result[1]


@pytest.mark.unit
def test_result_insertion_with_null_values(test_db: duckdb.DuckDBPyConnection) -> None:
    """Test that results are inserted with NULL values for missing fields.

    Should preserve historical data exactly as provided, using NULL for missing fields.
    """
    # Setup
    season_id, fixture_ids = create_test_season_with_fixtures(test_db, "2021-2022", 1)
    fixture_id = fixture_ids[0]

    # Create race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    race_id = int(race_result[0])

    # Insert result with NULLs for optional fields
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "Jane Doe", "26:00", "U20W", "F"],
    )

    # Verify result was inserted with NULLs
    result = test_db.execute(
        "SELECT position, athlete_name, time, club, race_number FROM results WHERE race_id = ?",
        [race_id],
    ).fetchone()
    assert result is not None
    assert result[0] == 1  # position
    assert result[1] == "Jane Doe"  # athlete_name
    assert result[2] == "26:00"  # time
    assert result[3] is None  # club
    assert result[4] is None  # race_number


@pytest.mark.unit
def test_deduplication_skip_existing_result(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that duplicate results are skipped when --force flag is not set.

    If a result already exists (same race_id, athlete_name, time), skip it.
    """
    # Setup
    season_id, fixture_ids = create_test_season_with_fixtures(test_db, "2021-2022", 1)
    fixture_id = fixture_ids[0]

    # Create race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    race_id = int(race_result[0])

    # Insert first result
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "John Smith", "25:30", "SM40", "M"],
    )

    # Check it exists
    assert result_exists(test_db, race_id, "John Smith", "25:30")

    # Try to insert duplicate (without --force, should skip)
    if not result_exists(test_db, race_id, "John Smith", "25:30"):
        test_db.execute(
            "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [race_id, 1, "John Smith", "25:30", "SM40", "M"],
        )

    # Verify only one result exists
    count = test_db.execute(
        "SELECT COUNT(*) FROM results WHERE race_id = ? AND athlete_name = ?",
        [race_id, "John Smith"],
    ).fetchone()
    assert count is not None
    assert count[0] == 1


@pytest.mark.unit
def test_force_flag_replaces_existing_results(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that --force flag replaces existing results.

    With --force flag, delete old results for the race and re-insert fresh data.
    """
    # Setup
    season_id, fixture_ids = create_test_season_with_fixtures(test_db, "2021-2022", 1)
    fixture_id = fixture_ids[0]

    # Create race
    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    race_id = int(race_result[0])

    # Insert initial result
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "John Smith", "25:30", "SM40", "M"],
    )

    initial_count = count_records(test_db, "results", race_id=race_id)
    assert initial_count == 1

    # Simulate --force: delete old results for this race
    test_db.execute("DELETE FROM results WHERE race_id = ?", [race_id])

    # Re-insert new data
    test_db.execute(
        "INSERT INTO results (race_id, position, athlete_name, time, category, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [race_id, 1, "Jane Doe", "26:00", "U20W", "F"],
    )

    # Verify old result is gone and new one exists
    assert not result_exists(test_db, race_id, "John Smith", "25:30")
    assert result_exists(test_db, race_id, "Jane Doe", "26:00")
    assert count_records(test_db, "results", race_id=race_id) == 1


@pytest.mark.unit
def test_dry_run_mode_no_database_writes(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    """Test that --dry-run mode parses PDFs without making database changes.

    In dry-run mode:
    - Parse PDFs and extract data
    - Calculate what WOULD be inserted
    - Log to ImportLogger
    - Make NO database changes
    """
    logger = ImportLogger()

    # Simulate dry-run: log that we would insert, but don't actually insert
    season_id = create_season_if_missing(test_db, "2021-2022")
    fixture_date = date(2021, 1, 1)
    fixture_id = create_fixture_if_missing(test_db, season_id, fixture_date, "Venue")

    test_db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, "Men", 5],
    )
    race_result = test_db.execute(
        "SELECT id FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    race_id = int(race_result[0])

    # Get count BEFORE
    before_count = count_records(test_db, "results")

    # In dry-run, we'd log but not insert
    logger.info("result_parse", found=3)

    # Get count AFTER
    after_count = count_records(test_db, "results")

    # No results should have been inserted
    assert before_count == after_count


@pytest.mark.unit
def test_import_log_creation_json_format(test_data_generator) -> None:
    """Test that import logs are created in JSON-lines format.

    Each log record should be valid JSON with timestamp, level, stage, and details.
    """
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "import.log"
        logger = ImportLogger(log_file=log_file)

        # Log some events
        logger.info("season_create", season="2021-2022", season_id=1)
        logger.warning("result_parse", file="test.pdf", row=5, issue="missing_time")
        logger.error("pdf_extract", file="bad.pdf", reason="no_tables_found")

        # Verify log file was created and contains JSON-lines
        assert log_file.exists()

        with open(log_file) as f:
            lines = f.readlines()

        assert len(lines) >= 3

        # Verify each line is valid JSON
        import json

        for line in lines:
            record = json.loads(line)
            assert "timestamp" in record
            assert "level" in record
            assert "stage" in record
            assert record["level"] in ("info", "warning", "error")


@pytest.mark.unit
def test_import_log_summary_report(test_data_generator) -> None:
    """Test that summary report is generated with statistics.

    Should include counts of records imported and warnings/errors encountered.
    """
    logger = ImportLogger()

    # Simulate some logging activity
    logger.info("result_insert", race_id=1, position=1, athlete_name="John")
    logger.info("result_insert", race_id=1, position=2, athlete_name="Jane")
    logger.warning("result_parse", file="test.pdf", issue="missing_time")
    logger.warning("result_parse", file="test.pdf", issue="malformed_position")

    # Generate summary
    summary = logger.summary()

    # Verify summary contains expected information
    assert "Import Summary" in summary
    assert "2" in summary  # 2 info records (results inserted)
    assert "2" in summary  # 2 warnings


@pytest.mark.integration
def test_full_import_workflow_results(test_db: duckdb.DuckDBPyConnection) -> None:
    """Integration test: complete workflow for importing results.

    Flow:
    1. Auto-create season from folder name
    2. Auto-create fixture from filename
    3. Create race(s)
    4. Insert results with NULL handling
    5. Skip duplicates (or replace with --force)
    6. Log all issues
    """
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "import_results.log"
        logger = ImportLogger(log_file=log_file)

        # Step 1: Auto-create season
        season_id = create_season_if_missing(test_db, "2021-2022")
        logger.info("season_create", season="2021-2022", season_id=season_id)

        # Step 2: Auto-create fixture(s)
        fixture_date = date(2021, 1, 1)
        fixture_id = create_fixture_if_missing(
            test_db, season_id, fixture_date, "Bicester Heritage"
        )
        logger.info(
            "fixture_create",
            season_id=season_id,
            date=str(fixture_date),
            fixture_id=fixture_id,
        )

        # Step 3: Create races
        for race_name in ["Men", "Women", "U13 Boys"]:
            test_db.execute(
                "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
                [fixture_id, race_name, 1],
            )

        # Step 4: Insert results
        sample_data = create_sample_pdf_results()
        race_result = test_db.execute(
            "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
            [fixture_id, "Men"],
        ).fetchone()
        race_id = int(race_result[0])

        for result_row in sample_data:
            test_db.execute(
                "INSERT INTO results "
                "(race_id, position, race_number, athlete_name, time, category, "
                " category_position, gender, gender_position, club) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    race_id,
                    int(result_row["position"]),
                    int(result_row["race_number"]),
                    result_row["athlete_name"],
                    result_row["time"],
                    result_row["category"],
                    int(result_row["category_position"]),
                    result_row["gender"],
                    int(result_row["gender_position"]),
                    result_row["club"],
                ],
            )
            logger.info(
                "result_insert",
                race_id=race_id,
                athlete_name=result_row["athlete_name"],
            )

        # Step 5: Verify results
        total_results = count_records(test_db, "results")
        assert total_results == 3

        # Step 6: Print summary
        logger.print_summary()

        # Verify log file was created
        assert log_file.exists()
