"""UI tests for the Rules and Constitution editor."""

from playwright.sync_api import Page, ConsoleMessage, Error


class TestRulesEditor:
    """Tests for the Rules and Constitution Quill editor."""

    def test_edit_page_loads(self, admin_browser: Page):
        """Edit page is accessible to admin users."""
        admin_browser.goto("http://localhost:8000/rules-and-constitution/edit")
        admin_browser.wait_for_load_state("networkidle")
        assert admin_browser.url.endswith("/rules-and-constitution/edit"), (
            f"Expected edit URL, got: {admin_browser.url}"
        )

    def test_quill_editor_is_visible(self, admin_browser: Page):
        """Quill editor container is rendered and visible on the edit page."""
        console_errors: list[str] = []
        page_errors: list[str] = []

        def capture_console(msg: ConsoleMessage) -> None:
            if msg.type == "error":
                console_errors.append(msg.text)

        def capture_page_error(exc: Error) -> None:
            page_errors.append(str(exc))

        admin_browser.on("console", capture_console)
        admin_browser.on("pageerror", capture_page_error)

        admin_browser.goto("http://localhost:8000/rules-and-constitution/edit")
        admin_browser.wait_for_load_state("networkidle")

        # Check for uncaught JS exceptions first
        assert not page_errors, (
            f"Uncaught JavaScript errors on editor page: {page_errors}"
        )

        # The Quill toolbar is injected by Quill; its presence means the editor mounted
        toolbar = admin_browser.locator(".ql-toolbar")
        assert toolbar.count() > 0, (
            f"Quill toolbar not found — JS console errors: {console_errors}"
        )
        assert toolbar.is_visible(), "Quill toolbar is not visible"

        # The editing area
        editor_area = admin_browser.locator(".ql-editor")
        assert editor_area.count() > 0, (
            f"Quill editor area not found — JS console errors: {console_errors}"
        )
        assert editor_area.is_visible(), "Quill editor area is not visible"

        assert not console_errors, f"JavaScript errors on editor page: {console_errors}"

    def test_quill_editor_via_navigation(self, admin_browser: Page):
        """Quill editor works when navigating from the view page via the Edit button."""
        page_errors: list[str] = []

        def capture_page_error(exc: Error) -> None:
            page_errors.append(str(exc))

        admin_browser.on("pageerror", capture_page_error)

        # Navigate to the view page first, then click edit (like the user does)
        admin_browser.goto("http://localhost:8000/rules-and-constitution")
        admin_browser.wait_for_load_state("networkidle")

        edit_link = admin_browser.locator("a:has-text('Edit')")
        assert edit_link.count() > 0, "Edit button not found on rules page"
        edit_link.click()
        admin_browser.wait_for_load_state("networkidle")

        assert admin_browser.url.endswith("/rules-and-constitution/edit"), (
            f"Expected edit URL, got: {admin_browser.url}"
        )

        assert not page_errors, f"Uncaught JS errors after clicking Edit: {page_errors}"

        toolbar = admin_browser.locator(".ql-toolbar")
        assert toolbar.count() > 0, "Quill toolbar not found after clicking Edit"
        assert toolbar.is_visible(), "Quill toolbar is not visible"

    def test_quill_scripts_loaded(self, admin_browser: Page):
        """All required JS scripts load successfully on the edit page."""
        failed_requests: list[str] = []

        def on_response(response):
            if response.status >= 400 and response.url.endswith(".js"):
                failed_requests.append(f"{response.url} -> {response.status}")

        admin_browser.on("response", on_response)
        admin_browser.goto("http://localhost:8000/rules-and-constitution/edit")
        admin_browser.wait_for_load_state("networkidle")

        assert not failed_requests, f"JS scripts failed to load: {failed_requests}"

        # Verify global objects are available
        has_quill = admin_browser.evaluate("typeof Quill !== 'undefined'")
        assert has_quill, "Quill global not available"

        has_table = admin_browser.evaluate("typeof quillBetterTable !== 'undefined'")
        assert has_table, (
            "quillBetterTable global not available — "
            "check that quill-better-table.min.js loaded and Quill was loaded first"
        )

    def test_editor_can_type_and_save(self, admin_browser: Page):
        """Admin can type in the editor and submit the form successfully."""
        admin_browser.goto("http://localhost:8000/rules-and-constitution/edit")
        admin_browser.wait_for_load_state("networkidle")

        editor_area = admin_browser.locator(".ql-editor")
        editor_area.wait_for(state="visible", timeout=5000)

        # Clear any existing content and type new content
        editor_area.click()
        admin_browser.keyboard.press("Control+A")
        editor_area.type("Test rules content from Playwright.")

        # Submit the form (scope to the rules form to avoid matching the navbar logout button)
        admin_browser.locator("#rules-form button[type='submit']").click()
        admin_browser.wait_for_load_state("networkidle")

        # Should redirect back to the view page
        assert admin_browser.url.endswith("/rules-and-constitution"), (
            f"Expected redirect to view page, got: {admin_browser.url}"
        )

        # Verify saved content appears
        page_text = admin_browser.inner_text("body")
        assert "Test rules content from Playwright." in page_text, (
            "Saved content not visible on view page"
        )
