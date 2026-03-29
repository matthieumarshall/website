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
        assert test_client.get("/news/create").status_code == 401

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
