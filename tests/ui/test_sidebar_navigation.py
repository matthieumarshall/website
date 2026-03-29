"""UI tests for sidebar navigation"""


class TestSidebarNavigation:
    """Test sidebar navigation links and active states"""

    def test_sidebar_visible_on_news_page(self, browser):
        """Sidebar renders on the news/home page"""
        browser.goto("http://localhost:8000/news")
        sidebar = browser.query_selector("nav[aria-label='Main navigation']")
        assert sidebar is not None

    def test_sidebar_has_all_links(self, browser):
        """Sidebar contains all expected navigation links"""
        browser.goto("http://localhost:8000/news")
        expected_names = [
            "Home / News",
            "Results",
            "Entries",
            "History",
            "Documentation",
            "Fixtures",
            "Events",
        ]
        for name in expected_names:
            link = browser.query_selector(
                f"nav[aria-label='Main navigation'] a:has-text('{name}')"
            )
            assert link is not None, f"Sidebar link '{name}' not found"

    def test_news_link_is_active_on_news_page(self, browser):
        """The Home / News link has the active class on /news"""
        browser.goto("http://localhost:8000/news")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/news"

    def test_navigate_to_results(self, browser):
        """Clicking Results navigates to /results"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Results')")
        browser.wait_for_url("**/results")
        assert "/results" in browser.url

    def test_results_link_is_active_on_results_page(self, browser):
        """The Results link has the active class on /results"""
        browser.goto("http://localhost:8000/results")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/results"

    def test_navigate_to_entries(self, browser):
        """Clicking Entries navigates to /entries"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Entries')")
        browser.wait_for_url("**/entries")
        assert "/entries" in browser.url

    def test_entries_link_is_active_on_entries_page(self, browser):
        """The Entries link has the active class on /entries"""
        browser.goto("http://localhost:8000/entries")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/entries"

    def test_navigate_to_history(self, browser):
        """Clicking History navigates to /history"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('History')")
        browser.wait_for_url("**/history")
        assert "/history" in browser.url

    def test_history_link_is_active_on_history_page(self, browser):
        """The History link has the active class on /history"""
        browser.goto("http://localhost:8000/history")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/history"

    def test_navigate_to_documentation(self, browser):
        """Clicking Documentation navigates to /documentation"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Documentation')")
        browser.wait_for_url("**/documentation")
        assert "/documentation" in browser.url

    def test_documentation_link_is_active_on_documentation_page(self, browser):
        """The Documentation link has the active class on /documentation"""
        browser.goto("http://localhost:8000/documentation")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/documentation"

    def test_navigate_to_fixtures(self, browser):
        """Clicking Fixtures navigates to /fixtures"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Fixtures')")
        browser.wait_for_url("**/fixtures")
        assert "/fixtures" in browser.url

    def test_fixtures_link_is_active_on_fixtures_page(self, browser):
        """The Fixtures link has the active class on /fixtures"""
        browser.goto("http://localhost:8000/fixtures")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/fixtures"

    def test_navigate_to_events(self, browser):
        """Clicking Events navigates to /events"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Events')")
        browser.wait_for_url("**/events")
        assert "/events" in browser.url

    def test_events_link_is_active_on_events_page(self, browser):
        """The Events link has the active class on /events"""
        browser.goto("http://localhost:8000/events")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/events"

    def test_sidebar_visible_on_login_page(self, browser):
        """Sidebar renders on the login page"""
        browser.goto("http://localhost:8000/login")
        sidebar = browser.query_selector("nav[aria-label='Main navigation']")
        assert sidebar is not None

    def test_only_one_active_link_per_page(self, browser):
        """Exactly one sidebar link is active on any given page"""
        for route in [
            "/news",
            "/results",
            "/entries",
            "/history",
            "/documentation",
            "/fixtures",
            "/events",
        ]:
            browser.goto(f"http://localhost:8000{route}")
            active_links = browser.query_selector_all(
                "nav[aria-label='Main navigation'] a.active"
            )
            assert len(active_links) == 1, (
                f"Expected exactly 1 active link on {route}, found {len(active_links)}"
            )

    def test_sidebar_toggle_visible_on_mobile(self, browser):
        """The sidebar toggle button is visible at mobile viewport width"""
        browser.set_viewport_size({"width": 375, "height": 667})
        browser.goto("http://localhost:8000/news")
        toggle_btn = browser.query_selector("button[data-bs-target='#sidebarMenu']")
        assert toggle_btn is not None
        assert toggle_btn.is_visible()

    def test_sidebar_toggle_expands_sidebar_on_mobile(self, browser):
        """Clicking the toggle button shows the sidebar on mobile"""
        browser.set_viewport_size({"width": 375, "height": 667})
        browser.goto("http://localhost:8000/news")
        toggle_btn = browser.query_selector("button[data-bs-target='#sidebarMenu']")
        assert toggle_btn is not None
        toggle_btn.click()
        browser.wait_for_timeout(400)  # Wait for Bootstrap collapse animation
        sidebar_menu = browser.query_selector("#sidebarMenu")
        assert sidebar_menu is not None
        classes = sidebar_menu.get_attribute("class") or ""
        assert "show" in classes
