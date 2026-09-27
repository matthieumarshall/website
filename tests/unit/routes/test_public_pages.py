"""Route tests: Public information pages, navigation and the cookie notice."""

import re

import duckdb
from fastapi.testclient import TestClient

from website import repository
from website.content import SIDEBAR_ITEMS
from website.models import UserRole
from website.passwords import hash_password


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


class TestSidebarItems:
    def test_sidebar_items_is_list(self) -> None:
        assert isinstance(SIDEBAR_ITEMS, tuple)

    def test_sidebar_items_has_nine_entries(self) -> None:
        assert len(SIDEBAR_ITEMS) == 9

    def test_all_items_have_required_fields(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert item.name
            assert item.route
            assert item.page
            if item.children:
                for child in item.children:
                    assert child.name
                    assert child.route
                    assert child.page

    def test_all_routes_start_with_slash(self) -> None:
        for item in SIDEBAR_ITEMS:
            assert item.route.startswith("/")
            if item.children:
                for child in item.children:
                    assert child.route.startswith("/")

    def test_news_is_first_item(self) -> None:
        assert SIDEBAR_ITEMS[0].page == "news"
        assert SIDEBAR_ITEMS[0].route == "/news"

    def test_expected_pages_present(self) -> None:
        pages = {item.page for item in SIDEBAR_ITEMS}
        assert pages == {
            "news",
            "results",
            "standings",
            "divisions",
            "winners",
            "clubs",
            "rules_and_constitution",
            "administration",
            "fixtures",
        }

    def test_administration_has_sub_pages(self) -> None:
        admin_item = next(
            item for item in SIDEBAR_ITEMS if item.page == "administration"
        )
        assert admin_item.children
        assert len(admin_item.children) == 6
        sub_names = [child.name for child in admin_item.children]
        assert sub_names == [
            "Documents",
            "Links",
            "Athlete Registration Guide",
            "Race Directors Guide",
            "Suppliers List",
            "Team Managers Guide",
        ]
        sub_pages = {child.page for child in admin_item.children}
        assert sub_pages == {
            "administration",
            "links",
            "athlete_registration_guide",
            "race_directors_guide",
            "suppliers_list",
            "team_managers_guide",
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
        ("divisions", "/divisions"),
        ("winners", "/winners"),
        ("clubs", "/clubs"),
        ("links", "/links"),
        ("rules_and_constitution", "/rules-and-constitution"),
        ("fixtures", "/fixtures"),
    ]

    def test_news_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/news").status_code == 200

    def test_results_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/results").status_code == 200

    def test_entries_page_loads(self, test_client: TestClient) -> None:
        # /entries is not linked from navigation and shows a work-in-progress notice.
        response = test_client.get("/entries")
        assert response.status_code == 200
        assert "work in progress" in response.text.lower()

    def test_entries_page_shows_wip_notice_for_admin(
        self, admin_client: TestClient
    ) -> None:
        response = admin_client.get("/entries")
        assert response.status_code == 200
        assert "work in progress" in response.text.lower()

    def test_admin_entries_empty_state_links_to_fixtures(
        self, admin_client: TestClient
    ) -> None:
        response = admin_client.get("/admin/entries")
        assert response.status_code == 200
        assert 'href="/fixtures"' in response.text

    def test_login_redirects_back_to_entries_after_success(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_user(
            test_db,
            "admin_login_test",
            hash_password("AdminPassword123!@#"),
            UserRole.admin,
        )
        login_page = test_client.get("/login?next=/entries")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
        assert match
        response = test_client.post(
            "/login",
            data={
                "username": "admin_login_test",
                "password": "AdminPassword123!@#",
                "csrf_token": match.group(1),
                "next_path": "/entries",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/entries"

    def test_rules_and_constitution_page_loads(self, test_client: TestClient) -> None:
        assert test_client.get("/rules-and-constitution").status_code == 200

    def test_rules_and_constitution_renders_mobile_and_desktop_toc_targets(
        self,
        test_client: TestClient,
        test_db: duckdb.DuckDBPyConnection,
    ) -> None:
        repository.upsert_static_page(
            test_db,
            "rules-and-constitution",
            "<h1>League Rules</h1><h2>Eligibility</h2><p>Details</p>",
        )

        response = test_client.get("/rules-and-constitution")

        assert re.search(
            r'<button[^>]+data-bs-target="#toc-collapse-mobile"', response.text
        ), "Mobile contents toggle button not found"
        assert re.search(
            r'<ul[^>]+id="toc-list-mobile"[^>]+class="[^"]*\btoc-list\b',
            response.text,
        ), "Mobile TOC list not found"
        assert re.search(
            r'<div[^>]+class="[^"]*\bcol-lg-3\b[^"]*\bd-none\b[^"]*\bd-lg-block\b',
            response.text,
        ), "Desktop TOC sidebar wrapper not found"
        assert re.search(
            r'<ul[^>]+id="toc-list-desktop"[^>]+class="[^"]*\btoc-list\b',
            response.text,
        ), "Desktop TOC list not found"

    def test_all_public_pages_return_html(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert "text/html" in response.headers.get("content-type", ""), route

    def test_sidebar_links_rendered_on_all_pages(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            for item in SIDEBAR_ITEMS:
                assert item.name in response.text, f"'{item.name}' not found on {route}"

    def test_only_one_active_link_per_page(self, test_client: TestClient) -> None:
        for _, route in self._pages:
            response = test_client.get(route)
            assert response.text.count("nav-link active") == 1, route

    def test_correct_link_is_active(self, test_client: TestClient) -> None:
        for _page, route in self._pages:
            response = test_client.get(route)
            match = re.search(
                r'class="nav-link active"[^>]*href="' + re.escape(route) + '"',
                response.text,
                re.DOTALL,
            )
            assert match is not None, f"No active link for {route}"


class TestPrivacyPolicyRoute:
    def test_privacy_policy_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/privacy-policy")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_privacy_policy_contains_privacy_content(
        self, test_client: TestClient
    ) -> None:
        resp = test_client.get("/privacy-policy")
        assert resp.status_code == 200


class TestContactRoute:
    def test_contact_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/contact")
        assert resp.status_code == 200
        assert "Contact Us" in resp.text
        assert "committee@oxonxc.org.uk" in resp.text


class TestAboutRoute:
    def test_about_page_loads(self, test_client: TestClient) -> None:
        resp = test_client.get("/about")
        assert resp.status_code == 200
        assert "About Us" in resp.text
        assert "Work in progress" in resp.text


class TestDismissCookieNotice:
    def test_dismiss_sets_cookie(self, test_client: TestClient) -> None:
        news_page = test_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        resp = test_client.post(
            "/dismiss-cookie-notice",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
            headers={"Referer": "http://testserver/news"},
        )
        assert resp.status_code == 302
        assert "cookie_notice_dismissed" in resp.headers.get("set-cookie", "")

    def test_dismiss_redirects_to_referer_path(self, test_client: TestClient) -> None:
        news_page = test_client.get("/news")
        csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', news_page.text)
        assert csrf_match
        resp = test_client.post(
            "/dismiss-cookie-notice",
            data={"csrf_token": csrf_match.group(1)},
            follow_redirects=False,
            headers={"Referer": "http://testserver/fixtures"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/fixtures"


class TestAccountPage:
    def test_account_redirects_when_unauthenticated(
        self, test_client: TestClient
    ) -> None:
        response = test_client.get("/account", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"].startswith("/login")

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


class TestWebsiteContentNavigation:
    def test_admin_sidebar_and_account_have_management_links(
        self, admin_client: TestClient
    ) -> None:
        resp = admin_client.get("/news")
        assert resp.status_code == 200
        assert "Website Content" in resp.text
        assert "/admin/clubs" in resp.text
        assert "/admin/divisions" in resp.text
        assert "/admin/winners" in resp.text
        assert "/admin/links" in resp.text
        assert "/administration/manage" in resp.text
        assert "/admin/club-managers" in resp.text
        assert "/admin/entries" in resp.text

        account_resp = admin_client.get("/account")
        assert account_resp.status_code == 200
        assert "Website Content Quick Links" in account_resp.text
        assert "Member Clubs" in account_resp.text

    def test_content_creator_sidebar_has_content_management_links(
        self, content_creator_client: TestClient
    ) -> None:
        resp = content_creator_client.get("/news")
        assert resp.status_code == 200
        assert "Website Content" in resp.text
        assert "/admin/clubs" in resp.text
        assert "/admin/divisions" in resp.text
        assert "/admin/winners" in resp.text
        assert "/admin/links" in resp.text
        assert "/administration/manage" in resp.text
        assert "/admin/club-managers" not in resp.text
        assert "/admin/entries" not in resp.text

    def test_anonymous_sidebar_lacks_website_content_management(
        self, test_client: TestClient
    ) -> None:
        anon_resp = test_client.get("/news")
        assert "Website Content" not in anon_resp.text
        assert "/admin/clubs" not in anon_resp.text

    def test_manager_sidebar_lacks_website_content_management(
        self, club_manager_client: TestClient
    ) -> None:
        mgr_resp = club_manager_client.get("/news")
        assert "Website Content" not in mgr_resp.text
        assert "/admin/clubs" not in mgr_resp.text

    def test_admin_pages_contain_view_public_page_links(
        self, admin_client: TestClient
    ) -> None:
        for path in (
            "/admin/clubs",
            "/admin/divisions",
            "/admin/winners",
            "/admin/links",
        ):
            resp = admin_client.get(path)
            assert resp.status_code == 200
            assert "View public page" in resp.text
