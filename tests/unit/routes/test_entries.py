"""Route tests: Club manager team entries: access guards and allocation limits."""

import re
from datetime import date, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.main import app
from website.models import EAAthlete, UserRole
from website.passwords import hash_password
from website.web.deps import get_athlete_directory


class _FakeAthleteDirectory:
    def __init__(self, athletes: list[dict[str, object]]) -> None:
        self._athletes = [EAAthlete.model_validate(a) for a in athletes]

    def fetch_club_athletes(self, ea_club_id: str) -> list[EAAthlete]:
        return self._athletes


class TestEntryBatchGuardsAndAllocation:
    def _seed_manager_entries_domain(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> dict[str, int | str]:
        season = repository.create_season(test_db, "Entries Guard Season")
        other_season = repository.create_season(test_db, "Entries Other Season")
        club = repository.create_club(
            test_db,
            name="Guard Test Club",
            oxl_code="GTC",
            ea_club_id="55555",
        )
        manager = repository.create_user(
            test_db,
            "guard_manager",
            hash_password("GuardPassword123!@#"),
            UserRole.club_manager,
        )
        repository.create_club_manager(
            test_db,
            user_id=manager.id,
            club_id=club.id,
            email="guard@example.com",
        )
        repository.upsert_season_entry_config(
            test_db,
            season_id=season.id,
            entries_open=True,
            ea_reference_date="2025-08-31",
            total_fixtures=5,
            junior_pence_per_fixture=200,
            adult_pence_per_fixture=300,
        )
        repository.create_fixture(
            test_db,
            season_id=season.id,
            title="Guard Fixture",
            date=(date.today() + timedelta(days=14)).isoformat(),
            location_name="Venue",
            address="Address",
            timetable=[],
            travel_instructions="",
        )
        return {
            "season_id": season.id,
            "other_season_id": other_season.id,
            "club_id": club.id,
            "manager_id": manager.id,
            "manager_username": "guard_manager",
            "manager_password": "GuardPassword123!@#",
        }

    def _login_manager(
        self,
        test_client: TestClient,
        username: str,
        password: str,
    ) -> None:
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        resp = test_client.post(
            "/login",
            data={
                "username": username,
                "password": password,
                "csrf_token": match.group(1),
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_entries_create_batch_rejects_when_allocation_insufficient(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        club_id = int(seeded["club_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        # Only one slot allocated, but two athletes will be submitted.
        repository.upsert_club_allocation(
            test_db, season_id, club_id, allocated_slots=1
        )

        athletes = _FakeAthleteDirectory(
            [
                {
                    "IndividualRef": 20001,
                    "FirstName": "Alice",
                    "LastName": "Runner",
                    "DateOfBirth": "2012-04-01",
                    "RegistrationStatus": "Registered",
                },
                {
                    "IndividualRef": 20002,
                    "FirstName": "Bob",
                    "LastName": "Runner",
                    "DateOfBirth": "2010-07-15",
                    "RegistrationStatus": "Registered",
                },
            ]
        )
        app.dependency_overrides[get_athlete_directory] = lambda: athletes

        add_page = test_client.get(f"/entries/{season_id}/add")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', add_page.text)
        assert csrf_match

        response = test_client.post(
            f"/entries/{season_id}/batch",
            data={
                "ea_urns": ["20001", "20002"],
                "csrf_token": csrf_match.group(1),
            },
            follow_redirects=False,
        )

        assert response.status_code == 403
        count = test_db.execute("SELECT COUNT(*) FROM entry_batches").fetchone()
        assert count
        assert count[0] == 0

    def test_batch_preview_404s_when_season_mismatch(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        other_season_id = int(seeded["other_season_id"])
        club_id = int(seeded["club_id"])
        manager_id = int(seeded["manager_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        batch = repository.create_entry_batch(
            test_db,
            season_id=season_id,
            club_id=club_id,
            manager_user_id=manager_id,
            fixtures_remaining_at_entry=2,
            total_pence=1000,
        )

        response = test_client.get(
            f"/entries/{other_season_id}/batch/{batch.id}/preview",
            follow_redirects=False,
        )
        assert response.status_code == 404

    def test_batch_checkout_404s_when_season_mismatch(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        seeded = self._seed_manager_entries_domain(test_db)
        season_id = int(seeded["season_id"])
        other_season_id = int(seeded["other_season_id"])
        club_id = int(seeded["club_id"])
        manager_id = int(seeded["manager_id"])
        self._login_manager(
            test_client,
            str(seeded["manager_username"]),
            str(seeded["manager_password"]),
        )

        batch = repository.create_entry_batch(
            test_db,
            season_id=season_id,
            club_id=club_id,
            manager_user_id=manager_id,
            fixtures_remaining_at_entry=2,
            total_pence=1000,
        )

        entries_page = test_client.get("/entries")
        csrf_match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', entries_page.text
        )
        assert csrf_match

        response = test_client.post(
            f"/entries/{other_season_id}/batch/{batch.id}/checkout",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
        )
        assert response.status_code == 404
