"""Route tests: What content creators may and may not do."""

import re

import duckdb
from fastapi.testclient import TestClient

from website import repository


class TestContentCreatorExtendedPermissions:
    def _get_csrf(
        self, client: TestClient, path: str = "/rules-and-constitution"
    ) -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_rules_and_constitution_edit_accessible_to_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        resp = content_creator_client.get("/rules-and-constitution/edit")
        assert resp.status_code == 200
        assert "Rules and Constitution" in resp.text

    def test_rules_and_constitution_edit_submit_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        csrf = self._get_csrf(content_creator_client, "/rules-and-constitution/edit")
        resp = content_creator_client.post(
            "/rules-and-constitution/edit",
            data={
                "csrf_token": csrf,
                "content": "<h2>Updated Rules</h2><p>New text</p>",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        page = repository.get_static_page(test_db, "rules-and-constitution")
        assert page is not None
        assert "Updated Rules" in page.content

    def test_administration_manage_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/administration/manage")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/administration/manage")
        create_resp = content_creator_client.post(
            "/administration/manage/sections",
            data={
                "title": "Creator Section",
                "slug": "creator-section",
                "description": "Added by creator",
                "csrf_token": csrf,
            },
        )
        assert create_resp.status_code == 200
        sections = repository.list_administration_sections(test_db)
        assert any(s.slug == "creator-section" for s in sections)

    def test_standings_recalculate_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Standings-Recalc-Season")
        resp = content_creator_client.get(f"/standings?season_id={season.id}")
        assert resp.status_code == 200
        assert "Calculate standings" in resp.text

        csrf = self._get_csrf(
            content_creator_client, f"/standings?season_id={season.id}"
        )
        post_resp = content_creator_client.post(
            "/standings/recalculate",
            data={"season_id": str(season.id), "csrf_token": csrf},
            follow_redirects=False,
        )
        assert post_resp.status_code == 303
        assert post_resp.headers["location"] == f"/standings?season_id={season.id}"

    def test_clubs_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/admin/clubs")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/clubs/new")
        create_resp = content_creator_client.post(
            "/admin/clubs",
            data={
                "name": "Creator Harriers",
                "oxl_code": "CRTR",
                "ea_club_id": "99991",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        clubs = repository.list_clubs(test_db)
        assert any(c.oxl_code == "CRTR" and c.name == "Creator Harriers" for c in clubs)

    def test_links_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        resp = content_creator_client.get("/admin/links")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/links/new")
        create_resp = content_creator_client.post(
            "/admin/links",
            data={
                "title": "Creator Link",
                "url": "https://example.com/creator",
                "category": "national",
                "description": "Test link",
                "sort_order": "1",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        links = repository.list_external_links(test_db)
        assert any(link.title == "Creator Link" for link in links)

    def test_divisions_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Div-Season")
        club = repository.create_club(test_db, "Div Club", "DVC", "12345")
        resp = content_creator_client.get("/admin/divisions")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/divisions")
        create_resp = content_creator_client.post(
            "/admin/divisions",
            data={
                "season_id": str(season.id),
                "club_id": str(club.id),
                "gender": "men",
                "division": "1",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        assignments = repository.list_division_assignments(test_db, season.id)
        assert len(assignments) == 1

    def test_winners_management_by_content_creator(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Win-Season")
        resp = content_creator_client.get("/admin/winners")
        assert resp.status_code == 200
        csrf = self._get_csrf(content_creator_client, "/admin/winners")
        create_resp = content_creator_client.post(
            "/admin/winners",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Men",
                "winner_name": "Fast Runner",
                "club": "Running Club",
                "total_score": "10",
                "note": "",
                "mode": "replace",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303
        winners = repository.list_winner_overrides(test_db)
        assert any(w.winner_name == "Fast Runner" for w in winners)

    def test_club_managers_and_entries_still_forbidden_for_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get(
            "/admin/club-managers", follow_redirects=False
        ).status_code in (302, 403)
        assert content_creator_client.get(
            "/admin/entries", follow_redirects=False
        ).status_code in (302, 403)
