"""Staff can set up per-race RaceTec URLs before importing results."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.parametrize("width", [375, 1280])
def test_add_race_and_save_url(admin_browser: Page, width: int) -> None:
    admin_browser.set_viewport_size({"width": width, "height": 900})
    race_name = f"UI setup race {width}"
    admin_browser.goto("http://localhost:8000/fixtures")
    admin_browser.locator("#season-panel [data-fixture-tab]").nth(1).click()
    panel = admin_browser.locator('[id^="fixture-sync-panel-"]')
    panel.get_by_role("button", name="Individual Race URLs").click()
    panel.get_by_label("Race name", exact=True).fill(race_name)
    panel.get_by_role("button", name="Add Race").click()

    panel = admin_browser.locator('[id^="fixture-sync-panel-"]')
    expect(panel.get_by_text("Race added.")).to_be_visible()
    race = panel.locator("section").filter(has_text=f"RaceTec URL — {race_name}")
    url = "https://www.racetecresults.com/results.aspx?CId=1&RId=2&EId=1"
    race.get_by_label("RaceTec results URL").fill(url)
    race.get_by_role("button", name="Save URL", exact=True).click()
    expect(panel.get_by_text("Sync configuration saved successfully.")).to_be_visible()
    expect(panel.get_by_role("button", name="Fetch Results Now")).to_be_enabled()
    expect(race.get_by_label("RaceTec results URL")).to_have_value(url)
    admin_browser.goto("http://localhost:8000/fixtures")
    admin_browser.locator("#season-panel [data-fixture-tab]").nth(1).click()
    panel.get_by_role("button", name="Individual Race URLs").click()
    expect(race.get_by_label("RaceTec results URL")).to_have_value(url)
