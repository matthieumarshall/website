"""UI tests for the Standings page."""

from playwright.sync_api import Page, expect

BASE = "http://localhost:8000"


class TestStandingsPage:
    """Tests for the public-facing /standings page."""

    def test_individual_filters_and_exports(self, browser: Page) -> None:
        browser.goto(f"{BASE}/standings?season_id=1")
        browser.get_by_role(
            "button", name="Individual standings for Senior Women"
        ).click()
        alice = browser.locator("[data-standing-row]").filter(has_text="Alice Smith")
        bob = browser.locator("[data-standing-row]").filter(has_text="Bob Jones")
        expect(alice).to_be_visible()
        club = browser.get_by_label("Filter by club")
        club.select_option(label="Oxford City AC")
        expect(alice).to_be_visible()
        expect(bob).to_be_hidden()
        name = browser.get_by_label("Search by name")
        name.fill("SMI")
        expect(alice).to_be_visible()
        link = browser.get_by_role("link", name="Export Senior Women standings as CSV")
        assert "club=Oxford+City+AC" in (link.get_attribute("href") or "")
        assert "name=SMI" in (link.get_attribute("href") or "")
        name.fill("missing")
        expect(
            browser.get_by_text("No standings match the current filters.")
        ).to_be_visible()
        browser.get_by_role(
            "button", name="Individual standings for SM", exact=True
        ).click()
        expect(browser.get_by_label("Search by name")).to_have_value("")

    def test_staff_action_tracks_season(self, admin_browser: Page) -> None:
        admin_browser.set_viewport_size({"width": 375, "height": 812})
        admin_browser.goto(f"{BASE}/standings?season_id=1")
        form = admin_browser.locator("#standings-recalculate form")
        expect(form.locator('[name="season_id"]')).to_have_value("1")
        box = form.bounding_box()
        assert box and box["x"] + box["width"] <= 375
        select = admin_browser.locator("#season-select")
        other = select.locator('option:not([value="1"])').first.get_attribute("value")
        assert other
        select.select_option(other)
        expect(form.locator('[name="season_id"]')).to_have_value(other)

    def test_team_division_filter_still_updates_rows_and_exports(
        self, browser: Page
    ) -> None:
        browser.goto(f"{BASE}/standings?season_id=1")
        browser.get_by_role("button", name="Team Standings").click()
        browser.get_by_role("button", name="Team standings for Senior Women").click()
        division = browser.get_by_label("Division")
        expect(division).to_be_visible()
        row = browser.locator("#standings-table-panel [data-team-division]").first
        expect(row).to_be_visible()
        division.select_option("1")
        link = browser.get_by_role("link", name="Export Senior Women standings as CSV")
        assert "division=1" in (link.get_attribute("href") or "")
        if row.get_attribute("data-team-division") != "1":
            expect(row).to_be_hidden()
        division.select_option("")
        expect(row).to_be_visible()
        assert "division=" not in (link.get_attribute("href") or "")

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

    def test_all_current_category_tabs_include_empty_categories(
        self, browser: Page
    ) -> None:
        """Current-format category tabs are present even without standings rows."""
        response = browser.request.get(
            f"{BASE}/standings/category-panel", params={"season_id": "1"}
        )
        assert response.ok
        body = response.text()
        assert 'aria-label="Individual standings for U10B"' in body
        assert 'aria-label="Individual standings for U18W"' in body
        team_response = browser.request.get(
            f"{BASE}/standings/category-panel",
            params={"season_id": "1", "standings_type": "team"},
        )
        assert 'aria-label="Team standings for U10G"' in team_response.text()
        assert 'aria-label="Team standings for Men"' in team_response.text()
        assert "U23M" not in body
        assert "U23W" not in body

        empty_table = browser.request.get(
            f"{BASE}/standings/table",
            params={
                "season_id": "1",
                "category": "U14B",
                "standings_type": "individual",
            },
        )
        assert empty_table.ok
        assert "No standings data available for U14B." in empty_table.text()

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

    def test_team_category_button_stays_active_after_click(self, browser: Page):
        """Clicking a team standings category button keeps it highlighted."""
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")

        browser.get_by_role("button", name="Team Standings").click()
        team_button = browser.locator(
            'nav[aria-label="Team category tabs"] button',
            has_text="Senior Women",
        ).first
        team_button.click()

        browser.wait_for_selector("text=Oxford City AC A")
        assert "active" in (team_button.get_attribute("class") or ""), (
            "Expected the clicked team category button to have the active class"
        )
        assert team_button.get_attribute("aria-pressed") == "true", (
            "Expected the clicked team category button to be aria-pressed true"
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


class TestStandingsTabBalance:
    """Tests that standings-tabs.js distributes tab buttons evenly across rows."""

    def test_no_js_errors_on_load(self, browser: Page):
        """standings-tabs.js produces no uncaught JavaScript errors."""
        page_errors: list[str] = []
        browser.on("pageerror", lambda e: page_errors.append(str(e)))
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        browser.wait_for_timeout(300)
        assert not page_errors, f"Uncaught JS errors: {page_errors}"

    def test_tab_buttons_have_uniform_width_when_wrapped(self, browser: Page):
        """When tab buttons wrap onto multiple rows, the JS gives them all the same width."""
        browser.set_viewport_size({"width": 600, "height": 800})
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        browser.wait_for_timeout(300)  # allow rAF callbacks to settle

        data = browser.evaluate("""
            () => {
                const result = {};
                document.querySelectorAll('nav.standings-tab-nav').forEach(nav => {
                    const label = nav.getAttribute('aria-label');
                    const container = nav.querySelector('[role="group"]');
                    const btns = Array.from(container ? container.querySelectorAll('button') : []);
                    if (!btns.length) return;
                    const firstTop = btns[0].getBoundingClientRect().top;
                    result[label] = {
                        widths: btns.map(b => b.offsetWidth),
                        wraps: btns.some(b => Math.round(b.getBoundingClientRect().top) > Math.round(firstTop) + 1)
                    };
                });
                return result;
            }
        """)

        # At 600 px there should be enough categories to force at least one group to wrap.
        assert any(v["wraps"] for v in data.values()), (
            "Expected at least one tab group to wrap at a 600 px viewport, "
            "but none did — the balancing code may not have been exercised."
        )

        for label, info in data.items():
            if not info["wraps"]:
                continue
            widths = info["widths"]
            assert all(abs(w - widths[0]) <= 1 for w in widths), (
                f"Non-uniform button widths in '{label}' after wrapping: {widths}"
            )

    def test_tab_buttons_do_not_overflow_container(self, browser: Page):
        """No tab button extends beyond the right edge of its flex container."""
        browser.set_viewport_size({"width": 600, "height": 800})
        browser.goto(f"{BASE}/standings")
        browser.wait_for_load_state("networkidle")
        browser.wait_for_timeout(300)

        overflowing = browser.evaluate("""
            () => Array.from(
                document.querySelectorAll('nav.standings-tab-nav [role="group"]')
            ).flatMap(container => {
                const right = container.getBoundingClientRect().right;
                return Array.from(container.querySelectorAll('button'))
                    .filter(b => b.getBoundingClientRect().right > right + 1)
                    .map(b => b.textContent.trim());
            })
        """)

        assert overflowing == [], f"Buttons overflow their container: {overflowing}"
