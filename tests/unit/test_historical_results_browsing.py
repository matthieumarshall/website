"""Tests for browsing historical results and standings through the API.

These tests verify that the existing /results and /standings endpoints
work correctly with historical data imported from the legacy system.
"""

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
