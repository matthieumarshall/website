"""Playwright UI tests for in-page editing and website content navigation."""

from playwright.sync_api import Page


class TestInPageEditingUI:
    """Verify in-page editing controls and sidebar management visibility."""

    def test_public_sidebar_lacks_management(self, browser: Page) -> None:
        """Website content links do not appear in the sidebar for public visitors."""
        browser.goto("http://localhost:8000/news")
        browser.wait_for_load_state("networkidle")
        sidebar_public = browser.locator("nav[aria-label='Main navigation']")
        assert sidebar_public.locator("text=Website Content").count() == 0
        assert sidebar_public.locator("a[href='/admin/clubs']").count() == 0

    def test_admin_sidebar_has_management(self, admin_browser: Page) -> None:
        """Website content links appear in the sidebar for admin."""
        admin_browser.goto("http://localhost:8000/news")
        admin_browser.wait_for_load_state("networkidle")
        sidebar_admin = admin_browser.locator("nav[aria-label='Main navigation']")
        assert sidebar_admin.locator("text=Website Content").is_visible()
        assert sidebar_admin.locator("a[href='/admin/clubs']").is_visible()
        assert sidebar_admin.locator("a[href='/admin/divisions']").is_visible()
        assert sidebar_admin.locator("a[href='/admin/winners']").is_visible()
        assert sidebar_admin.locator("a[href='/admin/links']").is_visible()

    def test_public_pages_lack_edit_controls(self, browser: Page) -> None:
        """Public visitor on /clubs, /links, /divisions sees no edit controls."""
        browser.goto("http://localhost:8000/clubs")
        browser.wait_for_load_state("networkidle")
        assert browser.locator("button:has-text('+ Add Club')").count() == 0
        assert browser.locator("th:has-text('Actions')").count() == 0

        browser.goto("http://localhost:8000/links")
        browser.wait_for_load_state("networkidle")
        assert browser.locator("button:has-text('+ Add Link')").count() == 0

        browser.goto("http://localhost:8000/divisions")
        browser.wait_for_load_state("networkidle")
        assert browser.locator("button:has-text('+ Assign Club')").count() == 0

    def test_admin_clubs_in_page_editing(self, admin_browser: Page) -> None:
        """Admin can toggle add form and open inline edit on /clubs."""
        admin_browser.goto("http://localhost:8000/clubs")
        admin_browser.wait_for_load_state("networkidle")
        add_btn = admin_browser.locator("button:has-text('+ Add Club')")
        assert add_btn.is_visible()

        # Expand the add club form
        add_btn.click()
        add_collapse = admin_browser.locator("#add-club-collapse")
        add_collapse.wait_for(state="visible", timeout=3000)
        assert add_collapse.locator("input[name='name']").is_visible()

        # Edit button is present on club rows
        first_edit_btn = admin_browser.locator(
            "#clubs-table-body button:has-text('Edit')"
        ).first
        if first_edit_btn.count() > 0:
            first_edit_btn.click()
            admin_browser.wait_for_selector(".card:has-text('Edit ')", timeout=3000)
            cancel_btn = admin_browser.locator("button:has-text('Cancel')").first
            assert cancel_btn.is_visible()
            cancel_btn.click()
            admin_browser.wait_for_load_state("networkidle")

    def test_admin_links_and_divisions_staff_controls(
        self, admin_browser: Page
    ) -> None:
        """Links and divisions pages show action controls to staff."""
        admin_browser.goto("http://localhost:8000/links")
        admin_browser.wait_for_load_state("networkidle")
        assert admin_browser.locator("button:has-text('+ Add Link')").is_visible()

        admin_browser.goto("http://localhost:8000/divisions")
        admin_browser.wait_for_load_state("networkidle")
        assert admin_browser.locator("button:has-text('+ Assign Club')").is_visible()
