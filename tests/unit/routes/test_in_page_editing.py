"""Route tests: HTMX in-page editing of clubs, links, divisions and winners."""

import re

import duckdb
from fastapi.testclient import TestClient

from website import repository


class TestClubsInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/clubs") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_public_view_has_no_edit_controls(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_club(test_db, "Public Club", "PUB", "123")
        resp = test_client.get("/clubs")
        assert resp.status_code == 200
        assert "Public Club" in resp.text
        assert "+ Add Club" not in resp.text
        assert 'hx-get="/clubs/' not in resp.text

    def test_inline_add_club_by_staff(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._csrf(content_creator_client, "/clubs")
        resp = content_creator_client.post(
            "/clubs/inline-add",
            data={
                "name": "Inline Harriers",
                "oxl_code": "INL",
                "ea_club_id": "8888",
                "opentrack_code": "INLH",
                "website_url": "https://example.com/inl",
                "is_oxfordshire_member": "on",
                "csrf_token": csrf,
            },
        )
        assert resp.status_code == 200
        assert "Inline Harriers" in resp.text
        assert 'id="club-row-' in resp.text
        row = test_db.execute("SELECT id FROM clubs WHERE oxl_code='INL'").fetchone()
        assert row is not None
        club = repository.get_club_by_id(test_db, row[0])
        assert club is not None
        assert club.name == "Inline Harriers"

    def test_inline_edit_and_toggle_club(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Toggle Club", "TGL", "777")
        form_resp = content_creator_client.get(f"/clubs/{club.id}/inline-form")
        assert form_resp.status_code == 200
        assert "Edit Toggle Club" in form_resp.text

        row_resp = content_creator_client.get(f"/clubs/{club.id}/inline-row")
        assert row_resp.status_code == 200
        assert "Toggle Club" in row_resp.text

        csrf = self._csrf(content_creator_client, "/clubs")
        edit_resp = content_creator_client.post(
            f"/clubs/{club.id}/inline-edit",
            data={
                "name": "Updated Club Name",
                "oxl_code": "TGL",
                "ea_club_id": "777",
                "opentrack_code": "",
                "website_url": "",
                "is_oxfordshire_member": "off",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Club Name" in edit_resp.text

        toggle_resp = content_creator_client.post(
            f"/clubs/{club.id}/inline-toggle",
            data={"csrf_token": csrf},
        )
        assert toggle_resp.status_code == 200
        updated = repository.get_club_by_id(test_db, club.id)
        assert updated is not None
        assert updated.is_active is False

    def test_anonymous_club_inline_access_rejected(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Auth Club", "ATH", "666")
        assert test_client.get(
            f"/clubs/{club.id}/inline-form", follow_redirects=False
        ).status_code in (302, 403)

    def test_club_manager_inline_access_rejected(
        self,
        club_manager_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        club = repository.create_club(test_db, "Auth Club 2", "ATH2", "667")
        assert club_manager_client.get(
            f"/clubs/{club.id}/inline-form", follow_redirects=False
        ).status_code in (302, 403)


class TestLinksInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/links") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_public_view_has_no_edit_controls(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_external_link(
            test_db,
            "Public Org",
            "https://example.com/org",
            "national",
            "Desc",
            0,
        )
        resp = test_client.get("/links")
        assert resp.status_code == 200
        assert "Public Org" in resp.text
        assert "+ Add Link" not in resp.text
        assert 'hx-get="/links/' not in resp.text

    def test_inline_add_and_edit_and_delete_link(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._csrf(content_creator_client, "/links")
        add_resp = content_creator_client.post(
            "/links/inline-add",
            data={
                "title": "Inline Link",
                "url": "https://example.com/inline",
                "category": "national",
                "description": "Added inline",
                "sort_order": "2",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert add_resp.status_code == 200
        assert "Inline Link" in add_resp.text
        link = next(
            link
            for link in repository.list_external_links(test_db)
            if link.title == "Inline Link"
        )

        form_resp = content_creator_client.get(f"/links/{link.id}/inline-form")
        assert form_resp.status_code == 200
        assert "Edit Link" in form_resp.text

        edit_resp = content_creator_client.post(
            f"/links/{link.id}/inline-edit",
            data={
                "title": "Updated Link Title",
                "url": "https://example.com/updated",
                "category": "national",
                "description": "Updated desc",
                "sort_order": "3",
                "is_active": "on",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Link Title" in edit_resp.text

        toggle_resp = content_creator_client.post(
            f"/links/{link.id}/inline-toggle",
            data={"csrf_token": csrf},
        )
        assert toggle_resp.status_code == 200
        assert "Hidden" in toggle_resp.text

        del_resp = content_creator_client.post(
            f"/links/{link.id}/inline-delete",
            data={"csrf_token": csrf},
        )
        assert del_resp.status_code == 200
        assert repository.get_external_link(test_db, link.id) is None


class TestDivisionsInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/divisions") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_divisions_inline_operations(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        season = repository.create_season(test_db, "Inline Div Season")
        club = repository.create_club(test_db, "Assign Club", "ASC", "1212")

        panel_resp = content_creator_client.get(
            f"/divisions/panel?season_id={season.id}"
        )
        assert panel_resp.status_code == 200
        assert "Division 1" in panel_resp.text

        csrf = self._csrf(content_creator_client, f"/divisions?season_id={season.id}")
        assign_resp = content_creator_client.post(
            "/divisions/inline-assign",
            data={
                "season_id": str(season.id),
                "club_id": str(club.id),
                "gender": "women",
                "division": "2",
                "csrf_token": csrf,
            },
        )
        assert assign_resp.status_code == 200
        assert "Assign Club" in assign_resp.text

        assignments = repository.list_division_assignments(test_db, season.id)
        assert len(assignments) == 1
        assign_id = assignments[0].id

        move_resp = content_creator_client.post(
            f"/divisions/assignments/{assign_id}/inline-move",
            data={
                "division": "1",
                "season_id": str(season.id),
                "csrf_token": csrf,
            },
        )
        assert move_resp.status_code == 200
        updated = repository.get_division_assignment(test_db, assign_id)
        assert updated is not None
        assert updated.division == 1

        del_resp = content_creator_client.post(
            f"/divisions/assignments/{assign_id}/inline-delete",
            data={
                "season_id": str(season.id),
                "csrf_token": csrf,
            },
        )
        assert del_resp.status_code == 200
        assert len(repository.list_division_assignments(test_db, season.id)) == 0


class TestWinnersInPageEditing:
    def _csrf(self, client: TestClient, path: str = "/winners") -> str:
        resp = client.get(path)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, f"CSRF token not found on {path}"
        return match.group(1)

    def test_winners_inline_operations(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        season = repository.create_season(test_db, "Inline Win Season")

        panel_resp = content_creator_client.get("/winners/tables-panel")
        assert panel_resp.status_code == 200
        assert "Individual winners" in panel_resp.text

        csrf = self._csrf(content_creator_client, "/winners")
        add_resp = content_creator_client.post(
            "/winners/inline-add",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Women",
                "winner_name": "Champion Athlete",
                "club": "Oxford City AC",
                "total_score": "4",
                "note": "Inline created",
                "mode": "replace",
                "csrf_token": csrf,
            },
        )
        assert add_resp.status_code == 200
        assert "Champion Athlete" in add_resp.text
        assert "Admin record" in add_resp.text

        override = next(
            o
            for o in repository.list_winner_overrides(test_db)
            if o.winner_name == "Champion Athlete"
        )
        form_resp = content_creator_client.get(
            f"/winners/overrides/{override.id}/inline-form"
        )
        assert form_resp.status_code == 200
        assert "Edit Winner Record" in form_resp.text

        edit_resp = content_creator_client.post(
            f"/winners/overrides/{override.id}/inline-edit",
            data={
                "season_id": str(season.id),
                "winner_type": "individual",
                "category": "Senior Women",
                "winner_name": "Updated Champion",
                "club": "Oxford City AC",
                "total_score": "3",
                "note": "Updated inline",
                "mode": "replace",
                "csrf_token": csrf,
            },
        )
        assert edit_resp.status_code == 200
        assert "Updated Champion" in edit_resp.text

        del_resp = content_creator_client.post(
            f"/winners/overrides/{override.id}/inline-delete",
            data={"csrf_token": csrf},
        )
        assert del_resp.status_code == 200
        assert repository.get_winner_override(test_db, override.id) is None
