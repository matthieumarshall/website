"""Test data generators for import testing.

Helper functions and classes for creating realistic test data for import script tests.
"""

from datetime import date

import duckdb


def create_sample_pdf_results() -> list[dict]:
    """Generate sample PDF result data for testing.

    Returns:
        List of result dictionaries as they would be parsed from a PDF
    """
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


def create_sample_standings_data() -> list[dict]:
    """Generate sample standings data for testing.

    Returns:
        List of standing dictionaries as they would be parsed from a PDF
    """
    return [
        {
            "position": "1",
            "athlete_name": "John Smith",
            "club": "Oxford AC",
            "total_score": "450",
            "rounds_competed": "5",
        },
        {
            "position": "2",
            "athlete_name": "Jane Doe",
            "club": "Harriers",
            "total_score": "430",
            "rounds_competed": "5",
        },
        {
            "position": "3",
            "athlete_name": "Mike Johnson",
            "club": "Harriers",
            "total_score": "420",
            "rounds_competed": "5",
        },
    ]


def create_malformed_results_data() -> list[dict]:
    """Generate sample malformed result data to test error handling.

    Returns:
        List of result dictionaries with various quality issues
    """
    return [
        {
            "position": "1",
            "athlete_name": "Valid Result",
            "time": "25:30",
            "category": "SM40",
            "gender": "M",
        },
        {
            "position": "invalid",  # malformed position
            "athlete_name": "Bad Position",
            "time": "26:00",
            "category": "SM40",
            "gender": "M",
        },
        {
            "position": "3",
            "athlete_name": "",  # missing athlete name
            "time": "27:00",
            "category": "SM40",
            "gender": "M",
        },
        {
            "position": "4",
            "athlete_name": "Missing Time",
            "time": "",  # missing time
            "category": "SM40",
            "gender": "M",
        },
    ]


def create_test_season_with_fixtures(
    con: duckdb.DuckDBPyConnection,
    season_name: str,
    num_fixtures: int = 3,
) -> tuple[int, list[int]]:
    """Create a season with multiple fixtures.

    Args:
        con: DuckDB connection
        season_name: Season name (e.g., "2021-2022")
        num_fixtures: Number of fixtures to create

    Returns:
        Tuple of (season_id, list of fixture_ids)
    """
    # Create season
    con.execute("INSERT INTO seasons (name) VALUES (?)", [season_name])
    season_result = con.execute(
        "SELECT id FROM seasons WHERE name = ?", [season_name]
    ).fetchone()
    assert season_result is not None, "Season should have been created"
    season_id = int(season_result[0])

    # Create fixtures
    fixture_ids = []
    for i in range(num_fixtures):
        day = (i * 7) + 1
        fixture_date = date(2021, 1, day)
        venue = f"Venue {i + 1}"
        con.execute(
            "INSERT INTO fixtures (season_id, date, title) VALUES (?, ?, ?)",
            [season_id, fixture_date, venue],
        )
        result = con.execute(
            "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
            [season_id, fixture_date],
        ).fetchone()
        assert result is not None, "Fixture should have been created"
        fixture_ids.append(int(result[0]))

    return season_id, fixture_ids


def count_records(con: duckdb.DuckDBPyConnection, table: str, **where_clause) -> int:
    """Count records in a table with optional WHERE clause.

    Args:
        con: DuckDB connection
        table: Table name
        **where_clause: Column=value pairs for WHERE clause

    Returns:
        Count of matching records
    """
    if not where_clause:
        result = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(result[0]) if result else 0

    columns = ", ".join(f"{k} = ?" for k in where_clause.keys())
    values = list(where_clause.values())
    query = f"SELECT COUNT(*) FROM {table} WHERE {columns}"
    result = con.execute(query, values).fetchone()
    return int(result[0]) if result else 0
