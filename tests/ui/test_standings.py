"""UI tests for the Standings page."""

from playwright.sync_api import Page


BASE = "http://localhost:8000"


class TestStandingsPage:
    """Tests for the public-facing /standings page."""

    def test_standings_page_loads(self, browser: Page):
        """Standings page renders without error."""
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        assert "/standings" in browser.url

    def test_standings_heading_visible(self, browser: Page):
        """Page heading 'Standings' is visible."""
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        heading = browser.locator("h1, h2, h3").filter(has_text="Standings").first
        assert heading.is_visible()

    def test_season_selector_present(self, browser: Page):
        """A season selector (select or link) is present on the standings page."""
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        # Expect a <select> for season or at least a reference to the seeded season
        content = browser.content()
        assert "UI Test Season 2026" in content

    def test_individual_standings_table_renders(self, browser: Page):
        """Individual standings table shows seeded athletes."""
        # Fetch the HTMX partial directly to verify template rendering
        response = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "Senior Women",
                "standings_type": "individual",
            },
        )
        assert response.ok, f"Expected 200, got {response.status}"
        body = response.text()
        assert "Alice Smith" in body, "First-place athlete not found in table"
        assert "Bob Jones" in body, "Second-place athlete not found in table"
        assert "Oxford City AC" in body

    def test_team_standings_table_renders(self, browser: Page):
        """Team standings table shows seeded team."""
        response = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "Senior Women",
                "standings_type": "team",
            },
        )
        assert response.ok, f"Expected 200, got {response.status}"
        body = response.text()
        assert "Oxford City AC A" in body, (
            "Seeded team not found in team standings table"
        )

    def test_individual_table_shows_position_and_score(self, browser: Page):
        """Individual standings table has position and total score columns."""
        response = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "Senior Women",
                "standings_type": "individual",
            },
        )
        body = response.text()
        assert "15" in body, "Total score for first place not found"
        assert "28" in body, "Total score for second place not found"

    def test_no_fromjson_error(self, browser: Page):
        """Navigating to standings produces no Jinja2 template errors."""
        page_errors: list[str] = []
        browser.on("pageerror", lambda exc: page_errors.append(str(exc)))
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        assert not page_errors, f"Unexpected page errors: {page_errors}"
