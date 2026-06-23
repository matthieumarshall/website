"""Unit tests for website.receipts — HTML and PDF generation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import duckdb
import pytest

from website.database import run_migrations
from website import repository
from website.auth import hash_password
from website.models import UserRole


# ---------------------------------------------------------------------------
# Helpers to set up a minimal paid batch in an in-memory DB
# ---------------------------------------------------------------------------


def _seed_paid_batch(db: duckdb.DuckDBPyConnection) -> int:
    """Create the minimal records needed to generate a receipt. Returns batch_id."""
    # User
    db.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        ["manager1", hash_password("pw"), UserRole.club_manager.value],
    )
    row = db.execute("SELECT id FROM users WHERE username='manager1'").fetchone()
    assert row is not None
    user_id = row[0]

    # Season
    db.execute(
        "INSERT INTO seasons (name) VALUES (?)",
        ["2025-26"],
    )
    row = db.execute("SELECT id FROM seasons WHERE name='2025-26'").fetchone()
    assert row is not None
    season_id = row[0]
    repository.create_club(
        db, name="Oxford City AC", oxl_code="OXC", ea_club_id="12345"
    )
    row = db.execute("SELECT id FROM clubs WHERE oxl_code='OXC'").fetchone()
    assert row is not None
    club_id = row[0]

    # Club manager
    repository.create_club_manager(db, user_id=user_id, club_id=club_id)

    # Entry batch (paid)
    db.execute(
        """
        INSERT INTO entry_batches
          (season_id, club_id, manager_user_id, status,
           fixtures_remaining_at_entry, total_pence,
           stripe_payment_method, paid_at)
        VALUES (?, ?, ?, 'paid', 3, 1500, 'card', ?)
        """,
        [season_id, club_id, user_id, datetime.now(timezone.utc)],
    )
    row = db.execute(
        "SELECT id FROM entry_batches WHERE club_id=? ORDER BY id DESC LIMIT 1",
        [club_id],
    ).fetchone()
    assert row is not None
    batch_id = row[0]

    # Athlete entry
    db.execute(
        """
        INSERT INTO athlete_entries
          (batch_id, season_id, club_id, ea_urn,
           athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence)
        VALUES (?, ?, ?, 12345678, 'Alice Jones', '1990-06-15', 'Senior', false, 1500)
        """,
        [batch_id, season_id, club_id],
    )

    return batch_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateHtmlReceipt:
    def test_returns_html_string(self):
        con = duckdb.connect(":memory:")
        run_migrations(con)
        batch_id = _seed_paid_batch(con)

        from website.receipts import generate_html_receipt

        html = generate_html_receipt(batch_id, con)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_html_contains_club_name(self):
        con = duckdb.connect(":memory:")
        run_migrations(con)
        batch_id = _seed_paid_batch(con)

        from website.receipts import generate_html_receipt

        html = generate_html_receipt(batch_id, con)
        assert "Oxford City AC" in html

    def test_html_contains_athlete_name(self):
        con = duckdb.connect(":memory:")
        run_migrations(con)
        batch_id = _seed_paid_batch(con)

        from website.receipts import generate_html_receipt

        html = generate_html_receipt(batch_id, con)
        assert "Alice Jones" in html

    def test_404_for_nonexistent_batch(self):
        from fastapi import HTTPException

        from website.receipts import generate_html_receipt

        con = duckdb.connect(":memory:")
        run_migrations(con)

        with pytest.raises(HTTPException) as exc_info:
            generate_html_receipt(9999, con)
        assert exc_info.value.status_code == 404

    def test_404_for_unpaid_batch(self):
        from fastapi import HTTPException

        from website.receipts import generate_html_receipt

        con = duckdb.connect(":memory:")
        run_migrations(con)
        batch_id = _seed_paid_batch(con)
        # Reset to pending
        con.execute(
            "UPDATE entry_batches SET status='pending_payment', paid_at=NULL WHERE id=?",
            [batch_id],
        )

        with pytest.raises(HTTPException) as exc_info:
            generate_html_receipt(batch_id, con)
        assert exc_info.value.status_code == 404


class TestGeneratePdfReceipt:
    def test_returns_bytes_with_mocked_weasyprint(self):
        import sys
        from types import ModuleType

        con = duckdb.connect(":memory:")
        run_migrations(con)
        batch_id = _seed_paid_batch(con)

        fake_pdf = b"%PDF-1.4 fake content"
        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.return_value = fake_pdf
        mock_weasyprint = ModuleType("weasyprint")
        setattr(mock_weasyprint, "HTML", MagicMock(return_value=mock_html_instance))

        # Inject mock module and clear any cached import of receipts
        original_weasyprint = sys.modules.get("weasyprint")
        original_receipts = sys.modules.get("website.receipts")
        sys.modules["weasyprint"] = mock_weasyprint
        # Remove cached receipts so it re-imports with mock weasyprint
        if "website.receipts" in sys.modules:
            del sys.modules["website.receipts"]

        try:
            from website.receipts import generate_pdf_receipt

            result = generate_pdf_receipt(batch_id, con)
        finally:
            # Restore original modules
            if original_weasyprint is None:
                sys.modules.pop("weasyprint", None)
            else:
                sys.modules["weasyprint"] = original_weasyprint
            if original_receipts is None:
                sys.modules.pop("website.receipts", None)
            else:
                sys.modules["website.receipts"] = original_receipts

        assert result == fake_pdf
        mock_html_cls = getattr(mock_weasyprint, "HTML")
        mock_html_cls.assert_called_once()
