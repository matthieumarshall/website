"""Browser checks for public information editing and status."""

import pytest
from playwright.sync_api import expect


def test_contact_default_survives_editor_round_trip(admin_browser):
    admin_browser.goto("http://localhost:8000/contact/edit")
    expect(admin_browser.locator(".ql-editor")).to_be_visible()
    admin_browser.get_by_role("button", name="Save Changes").click()
    expect(admin_browser.get_by_text("committee@oxonxc.org.uk")).to_be_visible()
    expect(
        admin_browser.get_by_text("If you encounter an issue", exact=False)
    ).to_be_visible()


@pytest.mark.parametrize("slug", ["about", "contact"])
def test_information_editor_saves_and_cancel_preserves(admin_browser, slug):
    admin_browser.goto(f"http://localhost:8000/{slug}")
    admin_browser.get_by_role("link", name="Edit", exact=True).click()
    editor = admin_browser.locator(".ql-editor")
    expect(editor).to_be_visible()
    editor.fill(f"Updated {slug} information")
    admin_browser.get_by_role("button", name="Save Changes").click()
    expect(admin_browser.get_by_text(f"Updated {slug} information")).to_be_visible()
    admin_browser.get_by_role("link", name="Edit", exact=True).click()
    admin_browser.locator(".ql-editor").fill("Discard this")
    admin_browser.get_by_role("link", name="Cancel").click()
    expect(admin_browser.get_by_text(f"Updated {slug} information")).to_be_visible()


def test_status_mobile_and_refresh(browser):
    browser.set_viewport_size({"width": 375, "height": 812})
    browser.goto("http://localhost:8000/status")
    expect(browser.get_by_role("heading", name="Website status")).to_be_visible()
    expect(browser.get_by_text("Storage usage")).to_be_visible()
    assert browser.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    with browser.expect_response("**/status/summary", timeout=35000):
        browser.wait_for_timeout(30500)
    blocked = browser.evaluate("""() => {
        const detail = {requestConfig: {path: '/status/summary'},
          xhr: {status: 429, getResponseHeader: () => '60'}};
        document.body.dispatchEvent(new CustomEvent('htmx:afterRequest', {detail}));
        return !document.body.dispatchEvent(new CustomEvent('htmx:beforeRequest',
          {detail, cancelable: true}));
    }""")
    assert blocked
    browser.get_by_role("link", name="Refresh", exact=True).click()
    expect(browser.get_by_role("heading", name="Website status")).to_be_visible()
