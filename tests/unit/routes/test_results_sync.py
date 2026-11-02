"""Route tests: Staff race results sync controls, on-demand trigger, settings, and CSV upload."""

import io
import re
from unittest.mock import AsyncMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.models import ParsedRaceWithResults, ParsedResult
from website.models.fixtures import TimetableEntry


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
        timetable=[TimetableEntry(time="11:00", event="Under 11 Girls Race")],
        travel_instructions="",
        tempo_results_url="https://www.racetecresults.com/results.aspx?CId=16418&RId=1006",
    )
    return season.id, fixture.id


class TestResultsSyncPermissions:
    def test_create_race_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        response = test_client.post(
            f"/fixtures/{fixture_id}/races",
            data={"csrf_token": "fake", "race_name": "Under 11 Girls Race"},
            follow_redirects=False,
        )
        assert response.status_code in (302, 403)

    def test_sync_panel_requires_staff(
        self, test_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        season_id, fixture_id = sync_fixture
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
    def test_empty_race_panel_offers_timetable_suggestions(
        self, admin_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        response = admin_client.get(f"/fixtures/{fixture_id}/sync-panel")
        assert response.status_code == 200
        assert "Individual Race URLs" in response.text
        assert "No races have been added" in response.text
        assert 'value="Under 11 Girls Race">11:00</option>' in response.text
        assert f'action="/fixtures/{fixture_id}/races"' in response.text

    def test_add_race_then_save_url(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
    ) -> None:
        season_id, fixture_id = sync_fixture
        first_fixture = repository.create_fixture(
            test_db, season_id, "Earlier", "2026-01-01", "Venue", "Address", [], ""
        )
        test_db.execute(
            "UPDATE fixtures SET tempo_results_url = NULL WHERE id = ?", [fixture_id]
        )
        csrf = _get_csrf(admin_client)
        response = admin_client.post(
            f"/fixtures/{fixture_id}/races",
            data={"csrf_token": csrf, "race_name": "  Under 11 Girls Race  "},
        )
        assert response.status_code == 200
        assert "Race added." in response.text
        assert 'class="accordion-collapse collapse show"' in response.text
        assert 'aria-label="Round 1: Round 5"' in response.text
        assert repository.list_races_for_fixture(test_db, first_fixture.id) == []
        races = repository.list_races_for_fixture(test_db, fixture_id)
        assert len(races) == 1
        assert races[0].name == "Under 11 Girls Race"
        assert f"racetec-url-{races[0].id}" in response.text
        assert 'title="Configure a results URL first"' in response.text
        url = "https://www.racetecresults.com/results.aspx?CId=1&RId=2&EId=1"
        response = admin_client.post(
            f"/fixtures/{fixture_id}/race/{races[0].id}/sync",
            data={"csrf_token": csrf, "racetec_url": url, "return_to_fixture": "true"},
        )
        assert response.status_code == 200
        assert f'id="fixture-sync-panel-{fixture_id}"' in response.text
        assert 'title="Configure a results URL first"' not in response.text
        saved = repository.get_race_by_id(test_db, races[0].id)
        assert saved is not None
        assert saved.racetec_url == url

        response = admin_client.post(
            f"/fixtures/{fixture_id}/race/{races[0].id}/sync",
            data={"csrf_token": csrf, "racetec_url": "", "return_to_fixture": "true"},
        )
        assert response.status_code == 200
        assert 'title="Configure a results URL first"' in response.text
        saved = repository.get_race_by_id(test_db, races[0].id)
        assert saved is not None
        assert saved.racetec_url is None

    @pytest.mark.parametrize(
        ("name", "status", "message"),
        [
            ("   ", 422, "Enter a race name."),
            ("  UNDER 11 GIRLS RACE ", 409, "A race with this name already exists"),
        ],
    )
    def test_add_race_validation(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
        name: str,
        status: int,
        message: str,
    ) -> None:
        _, fixture_id = sync_fixture
        repository.create_race(test_db, fixture_id, "Under 11 Girls Race")
        response = admin_client.post(
            f"/fixtures/{fixture_id}/races",
            data={"csrf_token": _get_csrf(admin_client), "race_name": name},
        )
        assert response.status_code == status
        assert message in response.text
        assert len(repository.list_races_for_fixture(test_db, fixture_id)) == 1

    def test_add_race_rejects_missing_csrf(
        self, admin_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        response = admin_client.post(
            f"/fixtures/{fixture_id}/races", data={"race_name": "Race"}
        )
        assert response.status_code in (403, 422)

    def test_sync_panel_renders_for_admin(
        self, admin_client: TestClient, sync_fixture: tuple[int, int]
    ) -> None:
        _, fixture_id = sync_fixture
        resp = admin_client.get(f"/fixtures/{fixture_id}/sync-panel")
        assert resp.status_code == 200
        assert "Race Results Integration" in resp.text
        assert "https://www.racetecresults.com" in resp.text

    def test_race_url_controls_render_in_fixture_and_results_areas(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
    ) -> None:
        season_id, fixture_id = sync_fixture
        race = repository.create_race(test_db, fixture_id, "Under 11 Girls Race")
        repository.update_race_racetec_url(
            test_db,
            race.id,
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2&EId=1",
        )

        fixture_response = admin_client.get(f"/fixtures/{fixture_id}/sync-panel")
        fixture_page = admin_client.get(f"/fixtures?season_id={season_id}")
        results_response = admin_client.get(
            f"/results/race-panel?fixture_id={fixture_id}"
        )

        assert fixture_response.status_code == 200
        assert fixture_page.status_code == 200
        assert results_response.status_code == 200
        for response in (fixture_response, fixture_page, results_response):
            assert f"racetec-url-{race.id}" in response.text
            assert "Under 11 Girls Race" in response.text

    @pytest.mark.parametrize("return_to_fixture", [False, True])
    def test_save_and_fetch_race_url_imports_only_selected_race(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        sync_fixture: tuple[int, int],
        return_to_fixture: bool,
    ) -> None:
        _, fixture_id = sync_fixture
        race = repository.create_race(test_db, fixture_id, "Under 11 Girls Race")
        csrf = _get_csrf(admin_client)
        racetec_url = "https://www.racetecresults.com/results.aspx?CId=1&RId=2&EId=1"
        scraped_races = [
            ParsedRaceWithResults(
                race_name="Under 11 Girls Race",
                results=[
                    ParsedResult(
                        position=1,
                        athlete_name="Selected Runner",
                        time="00:08:00",
                        category="U11G",
                        gender="Female",
                    )
                ],
            ),
            ParsedRaceWithResults(
                race_name="Senior Men's Race",
                results=[
                    ParsedResult(
                        position=1,
                        athlete_name="Unselected Runner",
                        time="00:29:00",
                        category="SM",
                        gender="Male",
                    )
                ],
            ),
        ]

        with patch(
            "website.services.results_sync.scrape_racetec_results",
            new_callable=AsyncMock,
            return_value=scraped_races,
        ) as scrape:
            response = admin_client.post(
                f"/fixtures/{fixture_id}/race/{race.id}/sync",
                data={
                    "csrf_token": csrf,
                    "racetec_url": racetec_url,
                    "sync_now": "true",
                    "return_to_fixture": str(return_to_fixture).lower(),
                },
            )

        assert response.status_code == 200
        assert "Imported 1 finishers" in response.text
        if return_to_fixture:
            assert f'id="fixture-sync-panel-{fixture_id}"' in response.text
        else:
            assert f'id="racetec-race-controls-{race.id}"' in response.text
        scrape.assert_awaited_once_with(racetec_url)
        saved_race = repository.get_race_by_id(test_db, race.id)
        assert saved_race is not None
        assert saved_race.racetec_url == racetec_url
        assert [
            result.athlete_name
            for result in repository.list_results_for_race(test_db, race.id)
        ] == ["Selected Runner"]

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
