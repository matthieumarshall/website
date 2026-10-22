"""Route tests: Staff race results sync controls, on-demand trigger, settings, and CSV upload."""

import io
import re
from unittest.mock import AsyncMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.models import ParsedRaceWithResults, ParsedResult


def _get_csrf(client: TestClient) -> str:
    resp = client.get("/fixtures")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
    assert match, "No CSRF token found"
    return match.group(1)


@pytest.fixture
def sync_fixture(test_db: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date="2026-03-01",
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
    )
    return season.id, fixture.id


class TestResultsSyncPermissions:
    def test_sync_panel_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = test_client.get(
            f"/fixtures/{fixture_id}/sync-panel", follow_redirects=False
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")

    def test_sync_now_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = test_client.post(
            f"/fixtures/{fixture_id}/sync",
            data={"csrf_token": "fake"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)

    def test_sync_settings_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = test_client.post(
            f"/fixtures/{fixture_id}/sync-settings",
            data={"csrf_token": "fake"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)

    def test_upload_csv_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = test_client.post(
            f"/fixtures/{fixture_id}/upload-results-csv",
            data={"csrf_token": "fake", "race_name": "Test"},
            files={"csv_file": ("test.csv", b"Pos,Name\n1,Athlete", "text/csv")},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)


class TestResultsSyncStaffOperations:
    def test_sync_panel_renders_for_admin(
        self, admin_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = admin_client.get(f"/fixtures/{fixture_id}/sync-panel")
        assert resp.status_code == 200
        assert "Race Results Integration" in resp.text
        assert "https://www.racetecresults.com" in resp.text

    def test_sync_settings_updates_auto_sync(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
    ) -> None:
        _, fixture_id = sync_fixture
        csrf = _get_csrf(admin_client)

        resp = admin_client.post(
            f"/fixtures/{fixture_id}/sync-settings",
            data={
                "csrf_token": csrf,
                "tempo_results_url": "https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
                "auto_sync_enabled": "true",
                "auto_sync_hours": "12",
                "auto_sync_interval_minutes": "10",
            },
        )
        assert resp.status_code == 200
        assert "Sync configuration saved successfully" in resp.text

        reloaded = repository.get_fixture_by_id(test_db, fixture_id)
        assert reloaded is not None
        assert reloaded.auto_sync_enabled is True
        assert reloaded.auto_sync_interval_minutes == 10
        assert reloaded.auto_sync_until is not None

    def test_sync_now_executes_and_recalculates(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
    ) -> None:
        _, fixture_id = sync_fixture
        csrf = _get_csrf(admin_client)

        mock_races = [
            ParsedRaceWithResults(
                race_name="Senior Men's Race",
                results=[
                    ParsedResult(
                        position=1,
                        race_number=1188,
                        athlete_name="Ben Cole",
                        time="00:27:10",
                        category="V40",
                        category_position=1,
                        gender="Male",
                        gender_position=1,
                        club="Swindon Harriers",
                    ),
                ],
            )
        ]

        with patch(
            "website.services.results_sync.scrape_racetec_results",
            new_callable=AsyncMock,
            return_value=mock_races,
        ):
            resp = admin_client.post(
                f"/fixtures/{fixture_id}/sync",
                data={"csrf_token": csrf},
            )
            assert resp.status_code == 200
            assert "Sync Successful" in resp.text
            assert "1 finishers across 1 races" in resp.text

        reloaded = repository.get_fixture_by_id(test_db, fixture_id)
        assert reloaded is not None
        assert reloaded.sync_status == "success"

        races = repository.list_races_for_fixture(test_db, fixture_id)
        assert len(races) == 1
        assert races[0].name == "Senior Men's Race"

    def test_upload_csv_fallback(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
    ) -> None:
        _, fixture_id = sync_fixture
        csrf = _get_csrf(admin_client)

        csv_content = (
            b"Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club\n"
            b"1,101,John Smith,00:30:00,SM,1,Male,1,Oxford City AC\n"
        )

        resp = admin_client.post(
            f"/fixtures/{fixture_id}/upload-results-csv",
            data={
                "csrf_token": csrf,
                "race_name": "Under 11 Boys",
            },
            files={"csv_file": ("results.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert resp.status_code == 200
        assert "Sync Successful" in resp.text
        assert "1 finishers across 1 races" in resp.text

        races = repository.list_races_for_fixture(test_db, fixture_id)
        assert any(r.name == "Under 11 Boys" for r in races)
