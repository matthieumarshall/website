"""UI tests for the /administration page layout."""


class TestAdministrationLayout:
    """The administration page renders sections in a two-column grid."""

    def test_page_loads(self, browser):
        """The administration page is accessible."""
        browser.goto("http://localhost:8000/administration")
        assert browser.title() != ""

    def test_grid_wrapper_present(self, browser):
        """A Bootstrap row with row-cols-md-2 wraps all sections."""
        browser.goto("http://localhost:8000/administration")
        grid = browser.query_selector(".row.row-cols-md-2")
        assert grid is not None, "Expected a .row.row-cols-md-2 grid wrapper"

    def test_sections_rendered_as_col_items(self, browser):
        """Each section is wrapped in a .col div inside the grid."""
        browser.goto("http://localhost:8000/administration")
        cols = browser.query_selector_all(".row.row-cols-md-2 > .col")
        assert len(cols) >= 2, f"Expected at least 2 .col items, got {len(cols)}"

    def test_sections_use_full_height_cards(self, browser):
        """Section cards have h-100 so they stretch to equal height in a row."""
        browser.goto("http://localhost:8000/administration")
        cards = browser.query_selector_all(".row.row-cols-md-2 .card.h-100")
        assert len(cards) >= 2, f"Expected at least 2 h-100 cards, got {len(cards)}"

    def test_section_headings_present(self, browser):
        """Each seeded section heading is visible on the page."""
        browser.goto("http://localhost:8000/administration")
        for title in ("Notices", "Agendas"):
            heading = browser.query_selector(f"h2:has-text('{title}')")
            assert heading is not None, f"Heading '{title}' not found"
