"""Route tests: The fixture calendar and its HTMX editing flows."""

import re

import duckdb
from fastapi.testclient import TestClient

from website import repository
from website.main import app
from website.services.uploads import IMAGE_POLICY, FileStore
from website.web.deps import get_image_store


class TestFixturesPublicPage:
    def test_fixtures_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures").status_code == 200

    def test_fixtures_page_no_login_required(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures").status_code == 200

    def test_fixtures_page_with_unknown_season_id(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/fixtures?season_id=9999")
        assert response.status_code == 200

    def test_season_panel_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/fixtures/season-panel").status_code == 200

    def test_fixture_detail_unknown_id_returns_404(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get(
            "/fixtures/fixture-detail?fixture_id=9999", follow_redirects=False
        )
        assert response.status_code == 404


class TestFixturesSeasonCrud:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        import re

        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match, "No CSRF token found"
        return match.group(1)

    def test_create_season_requires_auth(self, test_client: TestClient) -> None:
        response = test_client.post(
            "/fixtures/seasons",
            data={"name": "2025-2026", "csrf_token": "fake"},
            follow_redirects=False,
        )
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert response.headers["location"].startswith("/login")

    def test_create_season_as_admin(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/seasons",
            data={"name": "2025-2026", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        row = test_db.execute(
            "SELECT name FROM seasons WHERE name = ?", ["2025-2026"]
        ).fetchone()
        assert row is not None

    def test_create_season_as_content_creator(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        csrf = self._get_csrf(content_creator_client)
        resp = content_creator_client.post(
            "/fixtures/seasons",
            data={"name": "2024-2025", "csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        row = test_db.execute(
            "SELECT name FROM seasons WHERE name = ?", ["2024-2025"]
        ).fetchone()
        assert row is not None

    def test_delete_season_with_no_fixtures(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:

        season = repository.create_season(test_db, "2099-2100")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert repository.get_season_by_id(test_db, season.id) is None

    def test_delete_season_with_fixtures_returns_409(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:

        season = repository.create_season(test_db, "2088-2089")
        repository.create_fixture(
            test_db, season.id, "R1", "2088-09-01", "V", "A", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 409


class TestFixturesFixtureCrud:
    import json as _json

    def _get_csrf(self, client: TestClient) -> str:
        import re

        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_create_fixture_as_admin(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        import json

        season = repository.create_season(test_db, "2025-2026")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures",
            data={
                "title": "Round 1",
                "date": "2025-09-01",
                "location_name": "Town Hall",
                "address": "1 Main St",
                "timetable_json": json.dumps([{"event": "Start", "time": "09:00"}]),
                "travel_instructions": "Take the train.",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        fixtures = repository.list_fixtures_for_season(test_db, season.id)
        assert len(fixtures) == 1
        assert fixtures[0].title == "Round 1"

    def test_create_sixth_fixture_returns_409(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:

        season = repository.create_season(test_db, "2030-2031")
        for i in range(5):
            repository.create_fixture(
                test_db,
                season.id,
                f"Round {i + 1}",
                f"2030-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures",
            data={
                "title": "Round 6",
                "date": "2030-07-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 409

    def test_delete_fixture(
        self,
        admin_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:

        season = repository.create_season(test_db, "2031-2032")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2031-09-01", "V", "A", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert repository.get_fixture_by_id(test_db, fixture.id) is None

    def test_create_fixture_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/fixtures/seasons/1/fixtures",
            data={
                "title": "R",
                "date": "2025-01-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")

    def test_new_season_form_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new", follow_redirects=False)
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")


class TestFixturesCopy:
    def _get_csrf(self, client: TestClient) -> str:
        import re

        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_copy_form_requires_auth(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Copy-Auth-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2025-01-01", "V", "A", [], ""
        )
        resp = test_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/copy",
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")

    def test_copy_form_loads_as_admin(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        from website.models import TimetableEntry

        season = repository.create_season(test_db, "Copy-Form-Season")
        fixture = repository.create_fixture(
            test_db,
            season.id,
            "Source Fixture",
            "2025-06-01",
            "Town Hall",
            "1 Main St",
            [TimetableEntry(event="Start", time="09:00")],
            "Take the bus.",
        )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/copy",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Copy Fixture" in resp.text
        assert "Source Fixture" in resp.text
        assert "Save Copy" in resp.text

    def test_copy_form_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Copy-404-Season")
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/99999/copy",
            follow_redirects=False,
        )
        assert resp.status_code == 404


class TestFixturesSeasonPanelWithData:
    def test_season_panel_with_seasons_auto_selects_first(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "SPanel-Season-2025")
        repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = test_client.get("/fixtures/season-panel")
        assert resp.status_code == 200

    def test_season_panel_with_fixture_loads_images(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "SPanel-Imgs-2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-10-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo.jpg")
        resp = test_client.get(f"/fixtures/season-panel?season_id={season.id}")
        assert resp.status_code == 200


class TestFixtureDetailWithData:
    def test_fixture_detail_returns_200_for_existing_fixture(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "FDetail-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = test_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture.id}&season_id={season.id}"
        )
        assert resp.status_code == 200


class TestFixtureImageAltText:
    """Course map images include auto-generated alt text from fixture and season names."""

    def test_fixture_detail_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Alt Text Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1 Alt", "2025-09-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo.jpg")
        resp = test_client.get(
            f"/fixtures/fixture-detail?fixture_id={fixture.id}&season_id={season.id}"
        )
        assert resp.status_code == 200
        assert "Course map for Round 1 Alt, Alt Text Season 2025" in resp.text

    def test_season_panel_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Alt Panel Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 2 Alt", "2025-10-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo2.jpg")
        resp = test_client.get(f"/fixtures/season-panel?season_id={season.id}")
        assert resp.status_code == 200
        assert "Course map for Round 2 Alt, Alt Panel Season 2025" in resp.text

    def test_fixtures_page_image_has_correct_alt_text(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Alt Fixtures Season 2025")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 3 Alt", "2025-11-01", "Venue", "Addr", [], ""
        )
        repository.create_fixture_image(test_db, fixture.id, "photo3.jpg")
        resp = test_client.get(f"/fixtures?season_id={season.id}")
        assert resp.status_code == 200
        assert "Course map for Round 3 Alt, Alt Fixtures Season 2025" in resp.text

    def test_upload_response_has_correct_alt_text(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        tmp_path,  # noqa: ANN001
    ) -> None:

        season = repository.create_season(test_db, "Upload Alt Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Upload Round", "2025-09-01", "Venue", "Addr", [], ""
        )
        page = content_creator_client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        assert match
        csrf_token = match.group(1)

        # Redirect file writes to a temporary directory to avoid polluting data/
        app.dependency_overrides[get_image_store] = lambda: FileStore(
            tmp_path, IMAGE_POLICY
        )
        try:
            resp = content_creator_client.post(
                f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/images",
                files={"file": ("map.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
                data={"csrf_token": csrf_token},
            )
        finally:
            app.dependency_overrides.pop(get_image_store)

        assert resp.status_code == 200
        assert "Course map for Upload Round, Upload Alt Season" in resp.text

    def test_delete_response_remaining_images_have_correct_alt_text(
        self,
        content_creator_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
        tmp_path,  # noqa: ANN001
    ) -> None:

        season = repository.create_season(test_db, "Delete Alt Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Delete Round", "2025-09-01", "Venue", "Addr", [], ""
        )
        img1 = repository.create_fixture_image(test_db, fixture.id, "photo_a.jpg")
        repository.create_fixture_image(test_db, fixture.id, "photo_b.jpg")

        page = content_creator_client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        assert match
        csrf_token = match.group(1)

        app.dependency_overrides[get_image_store] = lambda: FileStore(
            tmp_path, IMAGE_POLICY
        )
        try:
            resp = content_creator_client.post(
                f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/images/{img1.id}/delete",
                data={"csrf_token": csrf_token},
            )
        finally:
            app.dependency_overrides.pop(get_image_store)

        assert resp.status_code == 200
        assert "Course map for Delete Round, Delete Alt Season" in resp.text


class TestFixturesNewSeasonForm:
    def test_new_season_form_loads_as_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/fixtures/seasons/new")
        assert resp.status_code == 200

    def test_new_season_form_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new", follow_redirects=False)
        assert resp.status_code in (302, 403)


class TestFixturesNewSeasonFormCancel:
    def test_cancel_returns_empty_fragment(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new-form-cancel")
        assert resp.status_code == 200
        assert resp.text.strip() == ""


class TestFixturesNewFixtureForm:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_new_fixture_form_loads_for_valid_season(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "NewFix-Form-Season")
        resp = admin_client.get(f"/fixtures/seasons/{season.id}/fixtures/new")
        assert resp.status_code == 200

    def test_new_fixture_form_returns_404_for_missing_season(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get(
            "/fixtures/seasons/99999/fixtures/new", follow_redirects=False
        )
        assert resp.status_code == 404

    def test_new_fixture_form_returns_409_when_season_full(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "Full-Season-NewFix")
        for i in range(5):
            repository.create_fixture(
                test_db,
                season.id,
                f"Round {i + 1}",
                f"2025-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/new", follow_redirects=False
        )
        assert resp.status_code == 409


class TestFixturesEditForm:
    def test_edit_form_loads_for_existing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "EditForm-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-09-01", "Venue", "Addr", [], ""
        )
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit"
        )
        assert resp.status_code == 200
        assert "Round 1" in resp.text

    def test_edit_form_returns_404_for_missing_season(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get(
            "/fixtures/seasons/99999/fixtures/1/edit", follow_redirects=False
        )
        assert resp.status_code == 404

    def test_edit_form_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        season = repository.create_season(test_db, "EditForm-NoFix-Season")
        resp = admin_client.get(
            f"/fixtures/seasons/{season.id}/fixtures/99999/edit",
            follow_redirects=False,
        )
        assert resp.status_code == 404


class TestFixturesUpdateFixture:
    def _get_csrf(self, client: TestClient) -> str:
        resp = client.get("/fixtures")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        return match.group(1)

    def test_update_fixture_changes_title(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json

        season = repository.create_season(test_db, "Update-Fixture-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "Old Title", "2025-09-01", "Venue", "Addr", [], ""
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit",
            data={
                "title": "New Title",
                "date": "2025-10-01",
                "location_name": "New Venue",
                "address": "New Addr",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        updated = repository.get_fixture_by_id(test_db, fixture.id)
        assert updated is not None
        assert updated.title == "New Title"

    def test_update_fixture_returns_404_for_missing_fixture(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json

        season = repository.create_season(test_db, "Update-Missing-Season")
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/99999/edit",
            data={
                "title": "Whatever",
                "date": "2025-10-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 404

    def test_update_fixture_requires_auth(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json

        season = repository.create_season(test_db, "Update-Auth-Season")
        fixture = repository.create_fixture(
            test_db, season.id, "R1", "2025-09-01", "V", "A", [], ""
        )
        resp = test_client.post(
            f"/fixtures/seasons/{season.id}/fixtures/{fixture.id}/edit",
            data={
                "title": "Hacked",
                "date": "2025-10-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": json.dumps([]),
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)

    def test_copy_submit_creates_fixture_in_target_season(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        import json

        source_season = repository.create_season(test_db, "Copy-Src-Season")
        target_season = repository.create_season(test_db, "Copy-Tgt-Season")
        from website.models import TimetableEntry

        fixture = repository.create_fixture(
            test_db,
            source_season.id,
            "Original",
            "2025-06-01",
            "Town Hall",
            "1 Main St",
            [TimetableEntry(event="Open", time="10:00")],
            "Bus route 42.",
        )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/copy",
            data={
                "season_id": str(target_season.id),
                "title": "Copy of Original",
                "date": "2026-06-01",
                "location_name": "Town Hall",
                "address": "1 Main St",
                "timetable_json": json.dumps([{"event": "Open", "time": "10:00"}]),
                "travel_instructions": "Bus route 42.",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        target_fixtures = repository.list_fixtures_for_season(test_db, target_season.id)
        assert len(target_fixtures) == 1
        assert target_fixtures[0].title == "Copy of Original"
        # source season unchanged
        assert len(repository.list_fixtures_for_season(test_db, source_season.id)) == 1
        assert (
            repository.list_fixtures_for_season(test_db, source_season.id)[0].id
            == fixture.id
        )

    def test_copy_submit_to_full_season_returns_409(
        self, admin_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:

        source_season = repository.create_season(test_db, "Copy-Full-Src")
        target_season = repository.create_season(test_db, "Copy-Full-Tgt")
        repository.create_fixture(
            test_db, source_season.id, "R0", "2025-01-01", "V", "A", [], ""
        )
        for i in range(5):
            repository.create_fixture(
                test_db,
                target_season.id,
                f"R{i + 1}",
                f"2025-0{i + 1}-01",
                "V",
                "A",
                [],
                "",
            )
        csrf = self._get_csrf(admin_client)
        resp = admin_client.post(
            "/fixtures/copy",
            data={
                "season_id": str(target_season.id),
                "title": "Overflow",
                "date": "2025-07-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 409

    def test_copy_submit_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/fixtures/copy",
            data={
                "season_id": "1",
                "title": "T",
                "date": "2025-01-01",
                "location_name": "V",
                "address": "A",
                "timetable_json": "[]",
                "travel_instructions": "",
                "csrf_token": "fake",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"].startswith("/login")
