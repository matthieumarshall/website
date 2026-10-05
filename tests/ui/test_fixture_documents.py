"""UI tests for fixture licence/assessment uploads and the copy-from picker."""

import io

from PIL import Image
from playwright.sync_api import Page

_BASE = "http://localhost:8000"


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 40), "navy").save(out, format="JPEG")
    return out.getvalue()


class TestFixtureDocuments:
    def test_admin_uploads_and_deletes_risk_assessment(
        self, admin_browser: Page
    ) -> None:
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")

        slot = admin_browser.locator("#fixture-document-risk_assessment")
        slot.locator("input[type='file']").set_input_files(
            files=[{"name": "risk.jpg", "mimeType": "image/jpeg", "buffer": _jpeg()}]
        )
        slot.locator("button:has-text('Upload')").click()

        link = admin_browser.locator("#fixture-document-risk_assessment a[href]")
        link.wait_for(timeout=10_000)
        assert "/fixture-docs/" in (link.get_attribute("href") or "")

        admin_browser.locator(
            "#fixture-document-risk_assessment button:has-text('Delete')"
        ).click()
        admin_browser.locator(
            "#fixture-document-risk_assessment:has-text('Not uploaded')"
        ).wait_for(timeout=10_000)

    def test_new_fixture_form_offers_copy_picker(self, admin_browser: Page) -> None:
        admin_browser.goto(f"{_BASE}/fixtures")
        admin_browser.wait_for_load_state("networkidle")
        admin_browser.locator("a[href$='/fixtures/new']").first.click()

        picker = admin_browser.locator("#copy-from-select")
        picker.wait_for(timeout=10_000)
        assert picker.locator("optgroup").count() >= 1

        picker.select_option(index=1)
        admin_browser.locator("button:has-text('Load details')").click()
        admin_browser.wait_for_load_state("networkidle")
        assert admin_browser.locator("input[name='copy_from_fixture_id']").count() == 1
        assert admin_browser.input_value("#fixture-title") != ""
