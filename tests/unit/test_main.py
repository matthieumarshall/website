"""Tests for FastAPI routes and main application"""

import re

from website.main import SIDEBAR_ITEMS


class TestHomeRoute:
    """Test home page endpoint"""

    def test_home_page_loads(self, test_client):
        """Test home page returns 200 status"""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_html_response(self, test_client):
        """Test home page returns HTML"""
        response = test_client.get("/")
        assert "text/html" in response.headers.get("content-type", "")

    def test_home_page_contains_title(self, test_client):
        """Test home page has title"""
        response = test_client.get("/")
        content = response.text.lower()
        assert "<title>" in content or "home" in content

    def test_home_page_unauthenticated_user(self, test_client):
        """Test home page accessible without authentication"""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_home_page_authenticated_user(
        self, test_client, test_user, test_user_creds
    ):
        """Test home page accessible with authentication"""
        # GET /login first to establish session and get CSRF token
        login_page = test_client.get("/login")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match, "No CSRF token found in login form"
        test_client.post(
            "/login",
            data={**test_user_creds, "csrf_token": match.group(1)},
            follow_redirects=True,
        )

        # Navigate to home
        response = test_client.get("/")
        assert response.status_code == 200


class TestLoginPageRoute:
    """Test GET /login endpoint"""

    def test_login_page_loads(self, test_client):
        """Test login page returns 200 status"""
        response = test_client.get("/login")
        assert response.status_code == 200


class TestSidebarItems:
    """Test the SIDEBAR_ITEMS navigation configuration"""

    def test_sidebar_items_is_list(self):
        assert isinstance(SIDEBAR_ITEMS, list)

    def test_sidebar_items_has_seven_entries(self):
        assert len(SIDEBAR_ITEMS) == 7

    def test_all_items_have_required_fields(self):
        for item in SIDEBAR_ITEMS:
            assert "name" in item, f"Item missing 'name': {item}"
            assert "route" in item, f"Item missing 'route': {item}"
            assert "page" in item, f"Item missing 'page': {item}"

    def test_all_routes_start_with_slash(self):
        for item in SIDEBAR_ITEMS:
            assert item["route"].startswith("/"), (
                f"Route does not start with /: {item['route']}"
            )

    def test_news_is_first_item(self):
        assert SIDEBAR_ITEMS[0]["page"] == "news"
        assert SIDEBAR_ITEMS[0]["route"] == "/news"

    def test_expected_pages_present(self):
        pages = {item["page"] for item in SIDEBAR_ITEMS}
        expected = {
            "news",
            "results",
            "entries",
            "history",
            "documentation",
            "fixtures",
            "events",
        }
        assert pages == expected


class TestHomeRedirect:
    """Test the root path redirects to /news"""

    def test_home_redirects_to_news(self, test_client):
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/news"

    def test_home_eventually_loads(self, test_client):
        response = test_client.get("/")
        assert response.status_code == 200


class TestNewPageRoutes:
    """Test the new sidebar page routes"""

    _pages = [
        ("news", "/news"),
        ("results", "/results"),
        ("entries", "/entries"),
        ("history", "/history"),
        ("documentation", "/documentation"),
        ("fixtures", "/fixtures"),
        ("events", "/events"),
    ]

    def test_news_page_loads(self, test_client):
        assert test_client.get("/news").status_code == 200

    def test_results_page_loads(self, test_client):
        assert test_client.get("/results").status_code == 200

    def test_entries_page_loads(self, test_client):
        assert test_client.get("/entries").status_code == 200

    def test_history_page_loads(self, test_client):
        assert test_client.get("/history").status_code == 200

    def test_documentation_page_loads(self, test_client):
        assert test_client.get("/documentation").status_code == 200

    def test_fixtures_page_loads(self, test_client):
        assert test_client.get("/fixtures").status_code == 200

    def test_events_page_loads(self, test_client):
        assert test_client.get("/events").status_code == 200

    def test_all_pages_return_html(self, test_client):
        for _, route in self._pages:
            response = test_client.get(route)
            assert "text/html" in response.headers.get("content-type", ""), (
                f"{route} did not return HTML"
            )

    def test_sidebar_links_rendered_on_all_pages(self, test_client):
        """All sidebar page names appear in each page's HTML"""
        for _, route in self._pages:
            response = test_client.get(route)
            for item in SIDEBAR_ITEMS:
                assert item["name"] in response.text, (
                    f"'{item['name']}' not found in {route} response"
                )

    def test_only_one_active_link_per_page(self, test_client):
        """Exactly one sidebar link has the active class on each page"""
        for _, route in self._pages:
            response = test_client.get(route)
            assert response.text.count("nav-link active") == 1, (
                f"Expected exactly one active link on {route}"
            )

    def test_correct_link_is_active(self, test_client):
        """The sidebar link for the current page has the active class"""
        for page, route in self._pages:
            response = test_client.get(route)
            # Template renders: <a class="nav-link active"\n href="/route">
            match = re.search(
                r'class="nav-link active"[^>]*href="' + re.escape(route) + '"',
                response.text,
                re.DOTALL,
            )
            assert match is not None, (
                f"No active link with href={route} found on {route} page"
            )
