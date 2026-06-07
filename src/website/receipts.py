"""PDF receipt generation using WeasyPrint."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
from fastapi import HTTPException
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path("templates")
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _build_receipt_context(
    batch_id: int, db: duckdb.DuckDBPyConnection
) -> dict[str, Any]:
    """Build the template context for a receipt. Raises 404 if batch not found or not paid."""
    from website import repository  # avoid circular import

    batch = repository.get_entry_batch(batch_id, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="Entry batch not found")
    if batch.status not in ("paid", "payment_initiated"):
        raise HTTPException(status_code=404, detail="Receipt not available")

    athlete_entries = repository.get_athlete_entries_for_batch(batch_id, db)
    club = repository.get_club_by_id(batch.club_id, db)
    manager = repository.get_user_by_id(db, batch.manager_user_id)
    season = repository.get_season_by_id(db, batch.season_id)

    paid_at_display = batch.paid_at.strftime("%d %b %Y %H:%M") if batch.paid_at else "—"
    method_map = {
        "card": "Card",
        "bacs_debit": "BACS Direct Debit",
    }
    payment_method_display = method_map.get(batch.stripe_payment_method or "", "—")

    return {
        "batch_id": batch.id,
        "athletes": athlete_entries,
        "club_name": club.name if club else "—",
        "manager_username": manager.username if manager else "—",
        "season_name": season.name if season else "—",
        "total_pence": batch.total_pence,
        "paid_at_display": paid_at_display,
        "payment_method_display": payment_method_display,
        "generated_at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    }


def generate_html_receipt(batch_id: int, db: duckdb.DuckDBPyConnection) -> str:
    """Render and return the receipt as an HTML string."""
    context = _build_receipt_context(batch_id, db)
    template = _templates.get_template("entries/receipt.html")
    return template.render(**context)


def generate_pdf_receipt(batch_id: int, db: duckdb.DuckDBPyConnection) -> bytes:
    """Generate a PDF receipt for a paid entry batch.

    Renders templates/entries/receipt.html via Jinja2, then converts to PDF
    bytes using WeasyPrint. Returns raw PDF bytes.

    Raises HTTPException(404) if the batch does not exist or is not paid/payment_initiated.
    """
    html_string = generate_html_receipt(batch_id, db)

    # Import here so WeasyPrint system libs are only required at PDF generation time
    from weasyprint import HTML  # noqa: PLC0415

    return HTML(string=html_string, base_url=str(_TEMPLATES_DIR)).write_pdf()
