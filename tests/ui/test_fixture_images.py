"""UI tests for the course map image display and modal (fixture-images.js)."""

import base64

from playwright.sync_api import Page


# Minimal valid 1×1 white pixel PNG — used as upload payload so no real file is needed.
_MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_MINIMAL_PNG = base64.b64decode(_MINIMAL_PNG_B64)

_BASE = "http://localhost:8000"


class TestFixtureImageModal:
    """Tests for the course map image thumbnail gallery and modal behaviour."""

    def test_fixtures_page_loads_for_admin(self, admin_browser: Page) -> None:
        """Fixtures page is accessible to admin users and shows seeded data."""
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")
        assert "/fixtures" in admin_browser.url

    def test_no_images_message_shown_before_upload(self, admin_browser: Page) -> None:
        """'No course map images uploaded yet' text is shown when there are no images."""
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")
        assert (
            admin_browser.locator("text=No course map images uploaded yet").count() > 0
        )

    def test_upload_course_map_image(self, admin_browser: Page) -> None:
        """Admin can upload a course map image and the thumbnail appears."""
        page_errors: list[str] = []
        admin_browser.on("pageerror", lambda e: page_errors.append(str(e)))

        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Set the file input to a minimal PNG in-memory (no real file on disk)
        file_input = admin_browser.locator("input[type='file'][name='file']").first
        file_input.set_input_files(
            files=[
                {
                    "name": "test_course_map.png",
                    "mimeType": "image/png",
                    "buffer": _MINIMAL_PNG,
                }
            ]
        )

        # Submit the upload form (HTMX swaps in the updated images partial)
        admin_browser.locator("button[type='submit']:has-text('Upload')").first.click()

        # Wait for HTMX to settle and the thumbnail to appear
        admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        assert not page_errors, f"Uncaught JS errors after upload: {page_errors}"
        thumbnail = admin_browser.locator(".fixture-image").first
        assert thumbnail.is_visible(), "Uploaded image thumbnail is not visible"

    def test_thumbnail_click_opens_modal(self, admin_browser: Page) -> None:
        """Clicking a course map thumbnail opens the modal dialog."""
        page_errors: list[str] = []
        admin_browser.on("pageerror", lambda e: page_errors.append(str(e)))

        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Ensure an image is present (upload one if not)
        if admin_browser.locator(".fixture-image").count() == 0:
            file_input = admin_browser.locator("input[type='file'][name='file']").first
            file_input.set_input_files(
                files=[
                    {
                        "name": "test_course_map.png",
                        "mimeType": "image/png",
                        "buffer": _MINIMAL_PNG,
                    }
                ]
            )
            admin_browser.locator(
                "button[type='submit']:has-text('Upload')"
            ).first.click()
            admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        thumbnail = admin_browser.locator(".fixture-image").first
        thumbnail.click()

        modal = admin_browser.locator("#fixture-image-modal")
        # <dialog> open attribute is set when showModal() is called
        assert modal.evaluate("el => el.open"), (
            "Modal dialog did not open after thumbnail click"
        )

        modal_img = admin_browser.locator("#fixture-image-modal-content")
        assert modal_img.is_visible(), "Modal image is not visible"
        # Modal src should have been populated by the JS handler
        modal_src = modal_img.get_attribute("src")
        assert modal_src and len(modal_src) > 0, "Modal image src is empty"

        assert not page_errors, f"Uncaught JS errors during modal test: {page_errors}"

    def test_modal_closes_on_escape_key(self, admin_browser: Page) -> None:
        """Pressing Escape closes the modal."""
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Ensure thumbnail exists
        if admin_browser.locator(".fixture-image").count() == 0:
            file_input = admin_browser.locator("input[type='file'][name='file']").first
            file_input.set_input_files(
                files=[
                    {
                        "name": "test_course_map.png",
                        "mimeType": "image/png",
                        "buffer": _MINIMAL_PNG,
                    }
                ]
            )
            admin_browser.locator(
                "button[type='submit']:has-text('Upload')"
            ).first.click()
            admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        admin_browser.locator(".fixture-image").first.click()
        modal = admin_browser.locator("#fixture-image-modal")
        assert modal.evaluate("el => el.open"), "Modal did not open"

        admin_browser.keyboard.press("Escape")
        assert not modal.evaluate("el => el.open"), "Modal did not close on Escape"

    def test_modal_closes_on_backdrop_click(self, admin_browser: Page) -> None:
        """Clicking the backdrop (outside modal content) closes the modal."""
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Ensure thumbnail exists
        if admin_browser.locator(".fixture-image").count() == 0:
            file_input = admin_browser.locator("input[type='file'][name='file']").first
            file_input.set_input_files(
                files=[
                    {
                        "name": "test_course_map.png",
                        "mimeType": "image/png",
                        "buffer": _MINIMAL_PNG,
                    }
                ]
            )
            admin_browser.locator(
                "button[type='submit']:has-text('Upload')"
            ).first.click()
            admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        admin_browser.locator(".fixture-image").first.click()
        modal = admin_browser.locator("#fixture-image-modal")
        assert modal.evaluate("el => el.open"), "Modal did not open"

        # Click the top-left corner of the dialog element itself (the backdrop area)
        modal.click(position={"x": 2, "y": 2})
        assert not modal.evaluate("el => el.open"), (
            "Modal did not close on backdrop click"
        )

    def test_modal_closes_on_close_button(self, admin_browser: Page) -> None:
        """Clicking the explicit × close button closes the modal."""
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Ensure thumbnail exists
        if admin_browser.locator(".fixture-image").count() == 0:
            file_input = admin_browser.locator("input[type='file'][name='file']").first
            file_input.set_input_files(
                files=[
                    {
                        "name": "test_course_map.png",
                        "mimeType": "image/png",
                        "buffer": _MINIMAL_PNG,
                    }
                ]
            )
            admin_browser.locator(
                "button[type='submit']:has-text('Upload')"
            ).first.click()
            admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        admin_browser.locator(".fixture-image").first.click()
        modal = admin_browser.locator("#fixture-image-modal")
        assert modal.evaluate("el => el.open"), "Modal did not open"

        admin_browser.locator(".fixture-image-modal-close").click()
        assert not modal.evaluate("el => el.open"), (
            "Modal did not close on close button click"
        )

    def test_thumbnail_keyboard_activation(self, admin_browser: Page) -> None:
        """Pressing Enter on a focused thumbnail opens the modal (keyboard accessibility)."""
        page_errors: list[str] = []
        admin_browser.on("pageerror", lambda e: page_errors.append(str(e)))

        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        # Ensure thumbnail exists
        if admin_browser.locator(".fixture-image").count() == 0:
            file_input = admin_browser.locator("input[type='file'][name='file']").first
            file_input.set_input_files(
                files=[
                    {
                        "name": "test_course_map.png",
                        "mimeType": "image/png",
                        "buffer": _MINIMAL_PNG,
                    }
                ]
            )
            admin_browser.locator(
                "button[type='submit']:has-text('Upload')"
            ).first.click()
            admin_browser.wait_for_selector(".fixture-image", timeout=10_000)

        thumbnail = admin_browser.locator(".fixture-image").first
        thumbnail.focus()
        admin_browser.keyboard.press("Enter")

        modal = admin_browser.locator("#fixture-image-modal")
        assert modal.evaluate("el => el.open"), "Modal did not open on Enter key"

        assert not page_errors, (
            f"Uncaught JS errors during keyboard test: {page_errors}"
        )

    def test_fixture_images_js_loads_without_errors(self, admin_browser: Page) -> None:
        """fixture-images.js loads without console errors on the fixtures page."""
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []

        admin_browser.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        admin_browser.on("pageerror", lambda e: page_errors.append(str(e)))
        admin_browser.on(
            "response",
            lambda r: (
                failed_requests.append(f"{r.url} -> {r.status}")
                if r.status >= 400 and r.url.endswith("fixture-images.js")
                else None
            ),
        )

        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        assert not failed_requests, (
            f"fixture-images.js failed to load: {failed_requests}"
        )
        assert not page_errors, f"Uncaught JS errors: {page_errors}"
        assert not console_errors, f"JS console errors: {console_errors}"
