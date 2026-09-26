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
            "Rules and Constitution",
            "Administration",
            "Fixtures",
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

    def test_navigate_to_rules_and_constitution(self, browser):
        """Clicking Rules and Constitution navigates to /rules-and-constitution"""
        browser.goto("http://localhost:8000/news")
        browser.click(
            "nav[aria-label='Main navigation'] a:has-text('Rules and Constitution')"
        )
        browser.wait_for_url("**/rules-and-constitution")
        assert "/rules-and-constitution" in browser.url

    def test_rules_and_constitution_link_is_active_on_rules_and_constitution_page(
        self, browser
    ):
        """The Rules and Constitution link has the active class on /rules-and-constitution"""
        browser.goto("http://localhost:8000/rules-and-constitution")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/rules-and-constitution"

    def test_administration_opens_sub_list(self, browser):
        """Clicking Administration opens the sub list of pages"""
        browser.goto("http://localhost:8000/news")
        submenu = browser.query_selector("#admin-submenu")
        assert submenu is not None
        # Submenu starts collapsed on news page
        browser.click("nav[aria-label='Main navigation'] a:has-text('Administration')")
        browser.wait_for_selector("#admin-submenu.show")
        expected_subpages = [
            "Documents",
            "Links",
            "Athlete Registration Guide",
            "Race Directors Guide",
            "Suppliers List",
            "Team Managers Guide",
        ]
        for name in expected_subpages:
            sub_link = browser.query_selector(f"#admin-submenu a:has-text('{name}')")
            assert sub_link is not None, f"Submenu link '{name}' not found"

    def test_navigate_to_administration_documents(self, browser):
        """Clicking Administration to open sub list, then Documents, navigates to /administration"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Administration')")
        browser.wait_for_selector("#admin-submenu.show")
        browser.click("#admin-submenu a:has-text('Documents')")
        browser.wait_for_url("**/administration")
        assert "/administration" in browser.url

    def test_navigate_to_links(self, browser):
        """Clicking Administration to open sub list, then Links, navigates to /links"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Administration')")
        browser.wait_for_selector("#admin-submenu.show")
        browser.click("#admin-submenu a:has-text('Links')")
        browser.wait_for_url("**/links")
        assert "/links" in browser.url

    def test_navigate_to_athlete_registration_guide(self, browser):
        """Clicking Administration to open sub list, then Athlete Registration Guide, navigates to guide"""
        browser.goto("http://localhost:8000/news")
        browser.click("nav[aria-label='Main navigation'] a:has-text('Administration')")
        browser.wait_for_selector("#admin-submenu.show")
        browser.click("#admin-submenu a:has-text('Athlete Registration Guide')")
        browser.wait_for_url("**/administration/athlete-registration-guide")
        assert "/administration/athlete-registration-guide" in browser.url

    def test_administration_link_is_active_on_administration_page(self, browser):
        """The Documents link has the active class on /administration and submenu is open"""
        browser.goto("http://localhost:8000/administration")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/administration"
        submenu = browser.query_selector("#admin-submenu.show")
        assert submenu is not None

    def test_links_link_is_active_on_links_page(self, browser):
        """The Links link has the active class on /links and submenu is open"""
        browser.goto("http://localhost:8000/links")
        active_link = browser.query_selector(
            "nav[aria-label='Main navigation'] a.active"
        )
        assert active_link is not None
        assert active_link.get_attribute("href") == "/links"
        submenu = browser.query_selector("#admin-submenu.show")
        assert submenu is not None

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

    def test_sidebar_visible_on_login_page(self, browser):
        """Sidebar renders on the login page"""
        browser.goto("http://localhost:8000/login")
        sidebar = browser.query_selector("nav[aria-label='Main navigation']")
        assert sidebar is not None

    def test_only_one_active_link_per_page(self, browser):
        """Exactly one sidebar link is active on any given page"""
        public_routes = [
            "/news",
            "/results",
            "/rules-and-constitution",
            "/administration",
            "/links",
            "/administration/athlete-registration-guide",
            "/fixtures",
        ]
        for route in public_routes:
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
