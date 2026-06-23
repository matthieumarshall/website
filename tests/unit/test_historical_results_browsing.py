"""Tests for browsing historical results and standings through the API.

These tests verify that the existing /results and /standings endpoints
work correctly with historical data imported from the legacy system.
"""

import json

import duckdb
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_results_endpoint_returns_200(test_client: TestClient) -> None:
    """Test that /results endpoint returns HTTP 200."""
    response = test_client.get("/results")
    assert response.status_code == 200


@pytest.mark.unit
def test_standings_endpoint_returns_200(test_client: TestClient) -> None:
    """Test that /standings endpoint returns HTTP 200."""
    response = test_client.get("/standings")
    assert response.status_code == 200


@pytest.mark.unit
def test_results_with_season_filter(test_client: TestClient) -> None:
    """Test that /results endpoint accepts season_id parameter."""
    response = test_client.get("/results?season_id=1")
    assert response.status_code == 200


@pytest.mark.unit
def test_standings_with_season_filter(test_client: TestClient) -> None:
    """Test that /standings endpoint accepts season_id parameter."""
    response = test_client.get("/standings?season_id=1")
    assert response.status_code == 200


@pytest.mark.unit
def test_standings_table_renders_round_scores(
    test_client: TestClient, test_db: duckdb.DuckDBPyConnection
) -> None:
    """Test that the standings table renders individual round scores."""
    test_db.execute("INSERT INTO seasons (name) VALUES (?)", ["2024-2025"])
    season_row = test_db.execute(
        "SELECT id FROM seasons WHERE name = ?", ["2024-2025"]
    ).fetchone()
    assert season_row is not None
    season_id = season_row[0]
    test_db.execute(
        "INSERT INTO fixtures (season_id, title, date, location_name, address) VALUES (?, ?, ?, ?, ?)",
        [season_id, "R1", "2025-01-01", "Test Venue", "Test Address"],
    )

    test_db.execute(
        "INSERT INTO individual_standings "
        "(season_id, category, position, athlete_name, club, "
        " total_score, rounds_competed, fixture_scores, is_imported) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, false)",
        [
            season_id,
            "Senior Women",
            1,
            "Alice Smith",
            "Oxford City AC",
            23,
            1,
            json.dumps({"r1": 23}),
        ],
    )

    response = test_client.get(
        "/standings/table",
        params={
            "season_id": season_id,
            "category": "Senior Women",
            "standings_type": "individual",
        },
    )

    assert response.status_code == 200
    assert "Alice Smith" in response.text
    assert "Oxford City AC" in response.text
    assert '<th scope="col" class="text-center">R1</th>' in response.text
    assert '<td class="text-center">23</td>' in response.text
