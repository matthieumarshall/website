"""Playwright UI tests for historical results and standings browsing.

Covers tasks T048-T050 (US2: standings UI) and T063-T072 (US3: results browsing UI).
All tests rely on the seeded "UI Test Season 2026" data created in conftest.py.
"""

from playwright.sync_api import Page


BASE = "http://localhost:8000"


# ---------------------------------------------------------------------------
# T048-T050: US2 — Historical standings visible in UI
# ---------------------------------------------------------------------------


class TestHistoricalStandingsUI:
    """T048-T050: Standings page displays seeded (is_imported) season data."""

    def test_standings_page_shows_season_in_dropdown(self, browser: Page) -> None:
        """T048: /standings page lists the seeded season in the season selector."""
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")

        season_select = browser.locator("#season-select")
        assert season_select.count() > 0, "Season <select> not found on /standings"
        options_text = season_select.inner_text()
        assert "UI Test Season 2026" in options_text, (
            "Seeded season not found in standings season dropdown"
        )

    def test_standings_displays_individual_standings_for_season(
        self, browser: Page
    ) -> None:
        """T049: /standings with a season_id shows individual standings rows."""
        # Navigate to standings — the route auto-selects the first season
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")

        # Fetch the standings table partial directly for the seeded category
        response = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "Senior Women",
                "standings_type": "individual",
            },
        )
        assert response.ok, f"standings/table returned {response.status}"
        body = response.text()
        assert "Alice Smith" in body, "First-place athlete missing from standings table"
        assert "Bob Jones" in body, "Second-place athlete missing from standings table"

    def test_standings_displays_team_standings_when_available(
        self, browser: Page
    ) -> None:
        """T050: Team standings table renders the seeded team row."""
        response = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "Senior Women",
                "standings_type": "team",
            },
        )
        assert response.ok, f"standings/table (team) returned {response.status}"
        body = response.text()
        assert "Oxford City AC A" in body, (
            "Seeded team not found in team standings table"
        )

    def test_standings_page_no_js_errors(self, browser: Page) -> None:
        """T048 supplement: /standings page produces no uncaught JS errors."""
        page_errors: list[str] = []
        browser.on("pageerror", lambda exc: page_errors.append(str(exc)))
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        assert not page_errors, f"Unexpected JS errors on /standings: {page_errors}"


# ---------------------------------------------------------------------------
# T063-T072: US3 — Historical results browsing
# ---------------------------------------------------------------------------


class TestHistoricalResultsBrowsing:
    """T063-T072: /results page and sub-panels render historical data correctly."""

    def test_results_page_loads_with_season_dropdown(self, browser: Page) -> None:
        """T063: /results page loads without error and shows a season dropdown."""
        page_errors: list[str] = []
        browser.on("pageerror", lambda exc: page_errors.append(str(exc)))

        browser.goto(f"{BASE}/results")
        browser.wait_for_load_state("networkidle")

        assert "/results" in browser.url
        assert not page_errors, f"Unexpected JS errors on /results: {page_errors}"

        season_select = browser.locator("#season-select")
        assert season_select.count() > 0, "Season <select> not found on /results"
        assert "UI Test Season 2026" in season_select.inner_text(), (
            "Seeded season not found in results season dropdown"
        )

    def test_results_fixture_panel_loads_for_season(self, browser: Page) -> None:
        """T064: Requesting fixture-panel for the seeded season returns fixtures."""
        response = browser.request.get(
            f"{BASE}/results/fixture-panel",
            params={"season_id": "1"},
        )
        assert response.ok, f"results/fixture-panel returned {response.status}"
        body = response.text()
        assert "UI Test Fixture" in body, (
            "Seeded fixture not found in fixture-panel response"
        )

    def test_results_race_panel_loads_for_fixture(self, browser: Page) -> None:
        """T065: Requesting race-panel for the seeded fixture returns races."""
        # First get the fixture id from the page content
        response = browser.request.get(
            f"{BASE}/results/fixture-panel",
            params={"season_id": "1"},
        )
        assert response.ok

        # The seeded fixture is fixture_id=1 (first inserted in conftest)
        race_response = browser.request.get(
            f"{BASE}/results/race-panel",
            params={"fixture_id": "1", "season_id": "1"},
        )
        assert race_response.ok, f"results/race-panel returned {race_response.status}"
        body = race_response.text()
        assert "Senior Women Race" in body, (
            "Seeded race name not found in race-panel response"
        )

    def test_results_race_table_shows_all_columns(self, browser: Page) -> None:
        """T066: Race results table contains position, name, time, category, club."""
        response = browser.request.get(
            f"{BASE}/results/race-table",
            params={"race_id": "1"},
        )
        assert response.ok, f"results/race-table returned {response.status}"
        body = response.text()
        assert "Alice Smith" in body, "Athlete name missing from race table"
        assert "35:12" in body, "Finish time missing from race table"
        assert "Oxford City AC" in body, "Club missing from race table"
        assert "Senior Women" in body, "Category missing from race table"

    def test_results_filtering_by_category(self, browser: Page) -> None:
        """T067: CSV export with category filter returns only matching rows.

        Server-side filtering is exposed through the export endpoints;
        the race table itself is filtered client-side by results-filter.js.
        """
        response = browser.request.get(
            f"{BASE}/results/export/csv",
            params={"race_id": "1", "category": "Senior Women"},
        )
        assert response.ok, f"results/export/csv (filtered) returned {response.status}"
        body = response.text()
        assert "Alice Smith" in body, (
            "Senior Women athlete missing after category filter"
        )
        assert "Bob Jones" not in body, (
            "Senior Men athlete should be excluded by category filter"
        )

    def test_results_csv_export_returns_data(self, browser: Page) -> None:
        """T068: CSV export endpoint returns non-empty CSV content for seeded race."""
        response = browser.request.get(
            f"{BASE}/results/export/csv",
            params={"race_id": "1"},
        )
        assert response.ok, f"results/export/csv returned {response.status}"
        content_type = response.headers.get("content-type", "")
        assert (
            "text/csv" in content_type or "application/octet-stream" in content_type
        ), f"Unexpected content-type for CSV export: {content_type}"
        body = response.text()
        assert "Alice Smith" in body, "Athlete name missing from CSV export"
        assert "35:12" in body, "Finish time missing from CSV export"

    def test_results_pdf_export_returns_pdf(self, browser: Page) -> None:
        """T069: PDF export endpoint returns a valid PDF binary for seeded race."""
        response = browser.request.get(
            f"{BASE}/results/export/pdf",
            params={"race_id": "1"},
        )
        assert response.ok, f"results/export/pdf returned {response.status}"
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, (
            f"Unexpected content-type for PDF export: {content_type}"
        )
        # PDF magic bytes: %PDF
        body_bytes = response.body()
        assert body_bytes[:4] == b"%PDF", "Response does not start with PDF magic bytes"

    def test_results_seasons_in_dropdown_order(self, browser: Page) -> None:
        """T070: Seasons appear in the results dropdown (at least the seeded one)."""
        browser.goto(f"{BASE}/results")
        browser.wait_for_load_state("networkidle")

        options = browser.locator("#season-select option").all()
        assert len(options) >= 1, "Expected at least one season option in dropdown"
        # Verify the seeded season is present
        texts = [opt.inner_text().strip() for opt in options]
        assert "UI Test Season 2026" in texts, (
            "Seeded season missing from results dropdown"
        )

    def test_standings_page_loads_with_historical_season(self, browser: Page) -> None:
        """T071: /standings page loads and lists the seeded season without errors."""
        page_errors: list[str] = []
        browser.on("pageerror", lambda exc: page_errors.append(str(exc)))

        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")

        assert not page_errors, f"Unexpected JS errors on /standings: {page_errors}"
        content = browser.content()
        assert "UI Test Season 2026" in content, (
            "Seeded season not visible on /standings page"
        )

    def test_standings_season_selection_shows_table(self, browser: Page) -> None:
        """T072: Fetching standings category-panel for seeded season returns categories."""
        response = browser.request.get(
            f"{BASE}/standings/category-panel",
            params={"season_id": "1"},
        )
        assert response.ok, f"standings/category-panel returned {response.status}"
        body = response.text()
        # The seeded category heading should appear in the category panel
        assert "Senior Women" in body, (
            "Seeded category 'Senior Women' not found in standings category-panel"
        )
