"""Club manager team entries: athlete selection, batches, checkout, receipts."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.models.forms import EntryBatchForm
from website.web.csrf import CsrfProtected
from website.web.deps import ClubManagerDep, Entries, ReceiptRendererDep, RendererDep

router = APIRouter(prefix="/entries/{season_id}")
_PAGE = "entries"
_BATCH = "/batch/{batch_id}"


@router.get("/add", response_class=HTMLResponse)
def entries_add_athletes(
    request: Request,
    season_id: int,
    session: ClubManagerDep,
    service: Entries,
    ui: RendererDep,
) -> HTMLResponse:
    """Show the club's athletes for selection."""
    selection = service.athlete_selection(season_id, session.club_manager)
    return ui.page(
        request,
        "entries/athlete_select.html",
        _PAGE,
        club_manager=session.club_manager,
        deadline_warning=None,
        view=selection,
    )


@router.post("/batch", response_class=HTMLResponse)
def entries_create_batch(
    season_id: int,
    form: Annotated[EntryBatchForm, Form()],
    session: ClubManagerDep,
    _csrf: CsrfProtected,
    service: Entries,
) -> RedirectResponse:
    """Create a pending-payment batch from the selected athletes."""
    batch = service.create_batch(
        season_id, session.club_manager, session.user.id, form.ea_urns
    )
    return RedirectResponse(
        f"/entries/{season_id}/batch/{batch.id}/preview", status_code=303
    )


@router.get(f"{_BATCH}/preview", response_class=HTMLResponse)
def entries_batch_preview(  # noqa: PLR0913 — FastAPI dependencies
    request: Request,
    season_id: int,
    batch_id: int,
    session: ClubManagerDep,
    service: Entries,
    ui: RendererDep,
) -> HTMLResponse:
    """Review a batch before paying."""
    preview = service.preview(season_id, batch_id, session.club_manager)
    return ui.page(
        request,
        "entries/batch_preview.html",
        _PAGE,
        club_name=session.club_manager.club_name,
        total_pence=preview.batch.total_pence,
        view=preview,
    )


@router.post(f"{_BATCH}/checkout", response_class=HTMLResponse)
def entries_batch_checkout(
    request: Request,
    season_id: int,
    batch_id: int,
    session: ClubManagerDep,
    _csrf: CsrfProtected,
    service: Entries,
) -> RedirectResponse:
    """Send the manager to Stripe Checkout (or on, if already paid)."""
    outcome = service.start_checkout(
        season_id,
        batch_id,
        session.club_manager,
        session.user.id,
        base_url=str(request.base_url).rstrip("/"),
    )
    return RedirectResponse(outcome.url, status_code=302 if outcome.started else 303)


@router.get(f"{_BATCH}/success", response_class=HTMLResponse)
def entries_batch_success(  # noqa: PLR0913 — FastAPI dependencies
    request: Request,
    season_id: int,
    batch_id: int,
    session: ClubManagerDep,
    service: Entries,
    ui: RendererDep,
) -> HTMLResponse:
    """Confirm a batch after returning from checkout."""
    season, batch = service.season_and_batch(season_id, batch_id, session.club_manager)
    return ui.page(
        request,
        "entries/batch_success.html",
        _PAGE,
        season=season,
        batch=batch,
        club_name=session.club_manager.club_name,
    )


@router.get(f"{_BATCH}/receipt", response_class=HTMLResponse)
def entries_batch_receipt_html(
    season_id: int,
    batch_id: int,
    session: ClubManagerDep,
    service: Entries,
    receipts: ReceiptRendererDep,
) -> HTMLResponse:
    """Show a paid batch's receipt."""
    receipt = service.receipt_for_manager(season_id, batch_id, session.club_manager)
    return HTMLResponse(content=receipts.html(receipt))


@router.get(f"{_BATCH}/receipt.pdf")
def entries_batch_receipt_pdf(
    season_id: int,
    batch_id: int,
    session: ClubManagerDep,
    service: Entries,
    receipts: ReceiptRendererDep,
) -> Response:
    """Download a paid batch's receipt as PDF."""
    receipt = service.receipt_for_manager(season_id, batch_id, session.club_manager)
    return Response(
        content=receipts.pdf(receipt),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt-{batch_id}.pdf"},
    )


@router.get("", response_class=HTMLResponse)
def entries_season_overview(
    request: Request,
    season_id: int,
    session: ClubManagerDep,
    service: Entries,
    ui: RendererDep,
) -> HTMLResponse:
    """Read-only list of every club's entered athletes for a season."""
    overview = service.season_entries(season_id)
    return ui.page(
        request,
        "entries/season_overview.html",
        _PAGE,
        club_manager=session.club_manager,
        view=overview,
    )
