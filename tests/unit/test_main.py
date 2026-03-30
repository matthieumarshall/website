"""Tests for FastAPI routes and main application"""

import re

import duckdb
from fastapi.testclient import TestClient

from website.main import SIDEBAR_ITEMS


class TestHomeRoute:
    """Test home page endpoint"""

    def test_home_page_loads(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_html_response(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert "text/html" in response.headers.get("content-type", "")

    def test_home_page_contains_title(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        content = response.text.lower()
        assert "<title>" in content or "home" in content

    def test_home_page_unauthenticated_user(self, test_client: TestClient) -> None:
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_authenticated_user(
        self,
        test_client: TestClient,
        test_user,  # noqa: ANN001
        test_user_creds: dict,  # noqa: ANN001
    ) -> None:
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        test_client.post(
            "/login",
            data={**test_user_creds, "csrf_token": match.group(1)},
            follow_redirects=True,
        )
        assert test_client.get("/").status_code == 200


class TestLoginPageRoute:
    def test_login_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/login").status_code == 200


class TestSidebarItems:
    def test_sidebar_items_is_list(self) -> None:
        assert isinstance(SIDEBAR_ITEMS, list)

    def test_sidebar_items_has_six_entries(self) -> None:
        assert len(SIDEBAR_ITEMS) == 6

    def test_all_items_have_required_fields(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert "name" in item
            assert "route" in item
            assert "page" in item

    def test_all_routes_start_with_slash(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert item["route"].startswith("/")

    def test_news_is_first_item(self) -> None:
        assert SIDEBAR_ITEMS[0]["page"] == "news"
        assert SIDEBAR_ITEMS[0]["route"] == "/news"

    def test_expected_pages_present(self) -> None:
        pages = {item["page"] for item in SIDEBAR_ITEMS}
        assert pages == {
            "news",
            "results",
            "entries",
            "rules_and_constitution",
            "administration",
            "fixtures",
        }


class TestHomeRedirect:
    def test_home_redirects_to_news(self, test_client: TestClient) -> None:
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/news"

    def test_home_eventually_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/").status_code == 200


class TestPublicPageRoutes:
    """Public pages (no auth required) return 200 HTML."""

    _pages = [
        ("news", "/news"),
        ("results", "/results"),
        ("entries", "/entries"),
        ("rules_and_constitution", "/rules-and-constitution"),
        ("fixtures", "/fixtures"),
    ]

    def test_news_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/news").status_code == 200

    def test_results_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/results").status_code == 200

    def test_entries_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/entries").status_code == 200

    def test_rules_and_constitution_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/rules-and-constitution").status_code == 200

    def test_all_public_pages_return_html(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert "text/html" in response.headers.get("content-type", ""), route

    def test_sidebar_links_rendered_on_all_pages(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            for item in SIDEBAR_ITEMS:
                assert item["name"] in response.text, (
                    f"'{item['name']}' not found on {route}"
                )

    def test_only_one_active_link_per_page(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert response.text.count("nav-link active") == 1, route

    def test_correct_link_is_active(self, test_client: TestClient) -> None:
        for page, route in self._pages:
            response = test_client.get(route)
            match = re.search(
                r'class="nav-link active"[^>]*href="' + re.escape(route) + '"',
                response.text,
                re.DOTALL,
            )
            assert match is not None, f"No active link for {route}"


class TestAdministrationAccess:
    def test_publicly_accessible(self, test_client: TestClient) -> None:
        assert test_client.get("/administration").status_code == 200

    def test_content_creator_can_access(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/administration").status_code == 200

    def test_admin_can_access(self, admin_client: TestClient) -> None:
        assert admin_client.get("/administration").status_code == 200


class TestNewsCrud:
    def test_news_page_accessible_to_public(self, test_client: TestClient) -> None:
        assert test_client.get("/news").status_code == 200

    def test_create_form_requires_auth(self, test_client: TestClient) -> None:
        response = test_client.get("/news/create", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    def test_create_form_available_to_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/news/create").status_code == 200

    def test_create_form_available_to_admin(self, admin_client: TestClient) -> None:
        assert admin_client.get("/news/create").status_code == 200

    def test_create_post_and_appears_on_news(
        self, content_creator_client: TestClient
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        resp = content_creator_client.post(
            "/news/create",
            data={
                "title": "Test Post",
                "content": "<p>Hello world</p>",
                "csrf_token": match.group(1),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Test Post" in resp.text

    def test_delete_post(
        self, content_creator_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        create_page = content_creator_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        content_creator_client.post(
            "/news/create",
            data={
                "title": "To Delete",
                "content": "<p>bye</p>",
                "csrf_token": match.group(1),
            },
        )
        posts = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["To Delete"]
        ).fetchall()
        assert len(posts) == 1
        post_id = posts[0][0]

        csrf_resp = content_creator_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', csrf_resp.text)
        assert csrf_match
        del_resp = content_creator_client.post(
            f"/news/{post_id}/delete",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=True,
        )
        assert del_resp.status_code == 200
        remaining = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["To Delete"]
        ).fetchall()
        assert remaining == []

    def test_other_user_cannot_edit_post(
        self,
        test_db: duckdb.DuckDBPyConnection,
        content_creator_client: TestClient,
        admin_client: TestClient,
    ) -> None:
        """A content_creator cannot edit a post authored by a different user."""
        # Admin creates a post
        create_page = admin_client.get("/news/create")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', create_page.text)
        assert match
        admin_client.post(
            "/news/create",
            data={
                "title": "Admin Post",
                "content": "<p>by admin</p>",
                "csrf_token": match.group(1),
            },
        )
        row = test_db.execute(
            "SELECT id FROM posts WHERE title = ?", ["Admin Post"]
        ).fetchone()
        assert row
        post_id = row[0]

        resp = content_creator_client.get(f"/news/{post_id}/edit")
        assert resp.status_code == 403


class TestNewsPagination:
    def test_page_query_param_accepted(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=1")
        assert resp.status_code == 200

    def test_out_of_range_page_returns_200(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=999")
        assert resp.status_code == 200

    def test_page_zero_clamped_to_one(self, test_client: TestClient) -> None:
        resp = test_client.get("/news?page=0")
        assert resp.status_code == 200


class TestAccountPage:
    def test_account_redirects_when_unauthenticated(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/account", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    def test_account_accessible_when_logged_in_as_admin(
        self, admin_client: TestClient
    ) -> None:
        assert admin_client.get("/account").status_code == 200

    def test_account_accessible_when_logged_in_as_content_creator(
        self, content_creator_client: TestClient
    ) -> None:
        assert content_creator_client.get("/account").status_code == 200

    def test_account_shows_username(self, admin_client: TestClient) -> None:
        response = admin_client.get("/account")
        assert response.status_code == 200
        assert "My Account" in response.text

    def test_account_shows_admin_role_badge(self, admin_client: TestClient) -> None:
        response = admin_client.get("/account")
        assert "Admin" in response.text

    def test_account_shows_content_creator_role_badge(
        self, content_creator_client: TestClient
    ) -> None:
        response = content_creator_client.get("/account")
        assert "Content Creator" in response.text


# ---------------------------------------------------------------------------
# Fixtures routes
# ---------------------------------------------------------------------------


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
            assert response.headers["location"] == "/login"

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
        from website import repository

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
        from website import repository

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
        from website import repository

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
        from website import repository

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
        from website import repository

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
            assert resp.headers["location"] == "/login"

    def test_new_season_form_requires_auth(self, test_client: TestClient) -> None:
        resp = test_client.get("/fixtures/seasons/new", follow_redirects=False)
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert resp.headers["location"] == "/login"
