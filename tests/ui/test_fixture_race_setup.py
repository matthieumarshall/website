"""Staff can upload and replace results per race from fixtures and results."""

import re
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.parametrize("width", [375, 1280])
def test_upload_results_from_fixtures_and_results(
    admin_browser: Page, width: int
) -> None:
    admin_browser.set_viewport_size({"width": width, "height": 900})
    race_name = f"UI setup race {width} {uuid4().hex[:8]}"
    admin_browser.goto("http://localhost:8000/fixtures")
    fixture_tab = admin_browser.locator("#season-panel [data-fixture-tab]").nth(1)
    fixture_title = fixture_tab.inner_text().split(". ", maxsplit=1)[1]
    fixture_tab.click()
    panel = admin_browser.locator("#fixture-detail")
    expect(panel.locator("h2.card-title")).to_have_text(fixture_title)
    panel.get_by_label("Race name", exact=True).fill(race_name)
    panel.get_by_role("button", name="Add Race").click()

    panel = admin_browser.locator("#fixture-detail")
    expect(panel.get_by_text("Race added.")).to_be_visible()
    race_upload = panel.locator('[id^="race-csv-upload-"]').filter(has_text=race_name)
    race_upload.locator('input[type="file"]').set_input_files(
        {
            "name": "first.csv",
            "mimeType": "text/csv",
            "buffer": (
                b"Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club\n"
                b"1,101,First UI Runner,00:30:00,Senior Men,1,Male,1,Oxford AC\n"
            ),
        }
    )
    race_upload.get_by_role("button", name="Upload and Replace Results").click()
    expect(
        panel.get_by_text("Imported 1 results. Protected manual results were kept.")
    ).to_be_visible()

    form = panel.locator('[id^="race-csv-upload-"]').filter(has_text=race_name)
    action = form.locator("form").get_attribute("action")
    assert action is not None
    match = re.search(r"/fixtures/(\d+)/race/(\d+)/upload-csv", action)
    assert match is not None
    fixture_id, race_id = match.groups()
    season_id = form.locator('input[name="season_id"]').input_value()

    admin_browser.goto(
        f"http://localhost:8000/results?season_id={season_id}"
        f"&fixture_id={fixture_id}&race_id={race_id}"
    )
    race_upload = admin_browser.locator(f"#race-csv-upload-{race_id}")
    race_upload.locator('input[type="file"]').set_input_files(
        {
            "name": "latest.csv",
            "mimeType": "text/csv",
            "buffer": (
                b"Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club\n"
                b"1,102,Latest UI Runner,00:29:00,Senior Men,1,Male,1,Oxford AC\n"
            ),
        }
    )
    race_upload.get_by_role("button", name="Upload and Replace Results").click()
    expect(
        admin_browser.locator("#race-table").get_by_text("Latest UI Runner")
    ).to_be_visible()
    expect(
        admin_browser.locator("#race-table").get_by_text("First UI Runner")
    ).to_have_count(0)
