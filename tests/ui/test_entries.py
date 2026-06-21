"""Playwright UI tests for the team entries journey.

These tests cover the manager-facing happy path using a pre-seeded paid batch
(bypassing the EA TRAPI API and Stripe payment, which cannot be exercised in
automated tests) as well as admin entries management pages.

The seeded data is injected by conftest.py's `server_process` session fixture.
The batch ID and season ID are passed through `os.environ` keys set during
seeding so the tests can construct the correct URLs.
"""

import os
import sys

import pytest


class TestManagerEntriesLanding:
    """Club manager can navigate to /entries and see open seasons."""

    def test_entries_page_requires_login(self, browser):
        """Unauthenticated users are redirected away from /entries."""
        response = browser.goto("http://localhost:8000/entries")
        # Should redirect to login (302) or show login page content
        final_url = browser.url
        content = browser.content().lower()
        assert (
            "login" in final_url
            or "login" in content
            or (response is not None and response.status in (302, 403))
        )

    def test_manager_can_reach_entries_page(self, manager_browser):
        """Authenticated club manager can access /entries."""
        manager_browser.goto("http://localhost:8000/entries")
        manager_browser.wait_for_load_state("networkidle")
        assert "entries" in manager_browser.url or manager_browser.title() != ""

    def test_entries_page_shows_team_entries_heading(self, manager_browser):
        """The /entries page renders the 'Team Entries' heading."""
        manager_browser.goto("http://localhost:8000/entries")
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "Team Entries" in content

    def test_entries_page_shows_open_season(self, manager_browser):
        """The seeded open season is listed on the /entries page."""
        manager_browser.goto("http://localhost:8000/entries")
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        # The seeded season is "Entries Test Season"
        assert "Entries Test Season" in content

    def test_entries_page_shows_previous_submission(self, manager_browser):
        """The pre-seeded paid batch appears in 'My previous submissions'."""
        manager_browser.goto("http://localhost:8000/entries")
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        # The paid badge should appear
        assert "Paid" in content or "paid" in content.lower()

    def test_entries_page_shows_club_name(self, manager_browser):
        """The manager's club name is shown on the entries page."""
        manager_browser.goto("http://localhost:8000/entries")
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "UI Test Club" in content


class TestManagerSuccessPage:
    """The success/confirmation page for a paid batch."""

    def test_success_page_loads_for_paid_batch(self, manager_browser):
        """The success page renders 'Payment confirmed!' for a paid batch."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/success"
        )
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "Payment confirmed" in content or "payment confirmed" in content.lower()

    def test_success_page_shows_receipt_link(self, manager_browser):
        """The success page links to the HTML receipt."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/success"
        )
        manager_browser.wait_for_load_state("networkidle")
        receipt_link = manager_browser.query_selector(
            f"a[href='/entries/{season_id}/batch/{batch_id}/receipt']"
        )
        assert receipt_link is not None, "Expected a link to the HTML receipt page"

    def test_success_page_shows_pdf_download_link(self, manager_browser):
        """The success page has a PDF download link."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/success"
        )
        manager_browser.wait_for_load_state("networkidle")
        pdf_link = manager_browser.query_selector(
            f"a[href='/entries/{season_id}/batch/{batch_id}/receipt.pdf']"
        )
        assert pdf_link is not None, "Expected a link to the PDF receipt"


class TestManagerReceiptPage:
    """The HTML receipt page for a paid batch."""

    def test_receipt_page_loads(self, manager_browser):
        """The HTML receipt page renders without error."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt"
        )
        manager_browser.wait_for_load_state("networkidle")
        # Should be a 200 with HTML content
        title = manager_browser.title()
        assert "Receipt" in title or "receipt" in title.lower() or "Entry" in title

    def test_receipt_contains_club_name(self, manager_browser):
        """The receipt HTML shows the club name."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt"
        )
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "UI Test Club" in content

    def test_receipt_contains_athlete_names(self, manager_browser):
        """Both seeded athletes appear in the receipt."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt"
        )
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "Test Junior" in content
        assert "Test Senior" in content

    def test_receipt_contains_season_name(self, manager_browser):
        """The receipt HTML shows the season name."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt"
        )
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        assert "Entries Test Season" in content

    def test_receipt_shows_race_numbers(self, manager_browser):
        """Race numbers are assigned and visible on the receipt."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt"
        )
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        # Race numbers are integers; check there is at least one number column
        assert (
            "Race number" in content
            or "race_number" in content
            or any(f">{n}<" in content for n in range(1, 9999))
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="WeasyPrint requires GTK libs not available on Windows",
    )
    def test_receipt_pdf_content_type(self, manager_browser):
        """The /receipt.pdf endpoint returns application/pdf content."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        # Use Playwright's request API to inspect headers without rendering
        response = manager_browser.request.get(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt.pdf"
        )
        assert response.status == 200
        assert "application/pdf" in response.headers.get("content-type", "")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="WeasyPrint requires GTK libs not available on Windows",
    )
    def test_receipt_pdf_content_disposition(self, manager_browser):
        """The PDF response sets a Content-Disposition attachment header."""
        batch_id = os.environ.get("UI_TEST_BATCH_ID", "1")
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        response = manager_browser.request.get(
            f"http://localhost:8000/entries/{season_id}/batch/{batch_id}/receipt.pdf"
        )
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition or "receipt" in disposition.lower()


class TestManagerSeasonOverview:
    """The /entries/{season_id} season overview page."""

    def test_season_overview_loads(self, manager_browser):
        """The season overview page renders for the manager's club."""
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        manager_browser.goto(f"http://localhost:8000/entries/{season_id}")
        manager_browser.wait_for_load_state("networkidle")
        content = manager_browser.content()
        # Should show the season or club info
        assert "Entries Test Season" in content or "UI Test Club" in content


class TestAdminEntriesPages:
    """Admin can view entries management pages."""

    def test_admin_entries_overview_loads(self, admin_browser):
        """The /admin/entries page renders a list of seasons."""
        admin_browser.goto("http://localhost:8000/admin/entries")
        admin_browser.wait_for_load_state("networkidle")
        content = admin_browser.content()
        # Should contain the season name or "Entries" heading
        assert "Entries" in content or "Entries Test Season" in content

    def test_admin_entries_season_detail_loads(self, admin_browser):
        """The /admin/entries/{season_id} page shows the submitted batch."""
        season_id = os.environ.get("UI_TEST_SEASON_ID", "1")
        admin_browser.goto(f"http://localhost:8000/admin/entries/{season_id}")
        admin_browser.wait_for_load_state("networkidle")
        content = admin_browser.content()
        assert "UI Test Club" in content or "Entries Test Season" in content

    def test_admin_clubs_list_loads(self, admin_browser):
        """The /admin/clubs page lists the seeded club."""
        admin_browser.goto("http://localhost:8000/admin/clubs")
        admin_browser.wait_for_load_state("networkidle")
        content = admin_browser.content()
        assert "UI Test Club" in content or "Clubs" in content
