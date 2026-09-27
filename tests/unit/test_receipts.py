"""Unit tests for entry receipts — building, and HTML and PDF rendering."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from website import repository
from website.db import run_migrations
from website.errors import NotFoundError
from website.models import UserRole
from website.passwords import hash_password
from website.services.entries import EntryService
from website.web.receipts import ReceiptRenderer
from website.web.rendering import Renderer

_TEMPLATES = Path("templates")


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    run_migrations(con)
    return con


def _html_receipt(batch_id: int, con: duckdb.DuckDBPyConnection) -> str:
    receipt = EntryService(con, MagicMock(), MagicMock()).receipt(batch_id)
    return _renderer().html(receipt)


def _renderer() -> ReceiptRenderer:
    return ReceiptRenderer(Renderer(_TEMPLATES).templates.env, _TEMPLATES)


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


class TestHtmlReceipt:
    def test_returns_html_string(self) -> None:
        con = _db()
        html = _html_receipt(_seed_paid_batch(con), con)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_html_contains_club_name(self) -> None:
        con = _db()
        assert "Oxford City AC" in _html_receipt(_seed_paid_batch(con), con)

    def test_html_contains_athlete_name(self) -> None:
        con = _db()
        assert "Alice Jones" in _html_receipt(_seed_paid_batch(con), con)

    def test_not_found_for_nonexistent_batch(self) -> None:
        with pytest.raises(NotFoundError):
            _html_receipt(9999, _db())

    def test_not_found_for_unpaid_batch(self) -> None:
        con = _db()
        batch_id = _seed_paid_batch(con)
        con.execute(
            "UPDATE entry_batches SET status='pending_payment', paid_at=NULL WHERE id=?",
            [batch_id],
        )
        with pytest.raises(NotFoundError):
            _html_receipt(batch_id, con)


class TestPdfReceipt:
    def test_returns_bytes_with_mocked_weasyprint(self) -> None:
        con = _db()
        receipt = EntryService(con, MagicMock(), MagicMock()).receipt(
            _seed_paid_batch(con)
        )
        fake_pdf = b"%PDF-1.4 fake content"
        html_cls = MagicMock()
        html_cls.return_value.write_pdf.return_value = fake_pdf

        with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=html_cls)}):
            result = _renderer().pdf(receipt)

        assert result == fake_pdf
        html_cls.assert_called_once()
