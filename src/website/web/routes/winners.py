"""The public past winners page with in-page (HTMX) editing for staff."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from website.errors import ValidationError
from website.models.forms import WinnerOverrideForm
from website.services.winners import WinnerService
from website.web.csrf import CsrfProtected
from website.web.deps import CurrentUserDep, RendererDep, Winners
from website.web.identity import is_staff
from website.web.rendering import Renderer
from website.web.security import RequireStaff

router = APIRouter(prefix="/winners")
_PAGE = "winners"
_PANEL = "_winners_tables_panel.html"


def _panel(
    request: Request,
    ui: Renderer,
    service: WinnerService,
    *,
    staff: bool = True,
    error: str | None = None,
) -> HTMLResponse:
    return ui.page(
        request,
        _PANEL,
        _PAGE,
        status_code=422 if error else 200,
        winners_by_type=service.winners_by_type(),
        is_staff=staff,
        error=error,
    )


@router.get("", response_class=HTMLResponse)
def winners(request: Request, service: Winners, ui: RendererDep) -> HTMLResponse:
    """Show official standings winners and administrative corrections."""
    return ui.page(
        request,
        "winners.html",
        _PAGE,
        winners_by_type=service.winners_by_type(),
        seasons=service.list_seasons(),
        is_staff=is_staff(request),
    )


@router.get("/tables-panel", response_class=HTMLResponse)
def winners_tables_panel(
    request: Request, service: Winners, ui: RendererDep
) -> HTMLResponse:
    """HTMX: refresh the winners tables."""
    return _panel(request, ui, service, staff=is_staff(request))


@router.post("/inline-add", response_class=HTMLResponse)
def winners_inline_add(  # noqa: PLR0913 — FastAPI dependencies
    request: Request,
    form: Annotated[WinnerOverrideForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    service: Winners,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: add a winner override and refresh the tables."""
    try:
        service.create(form, user.id if user else None)
    except ValidationError as exc:
        return _panel(request, ui, service, error=exc.message)
    return _panel(request, ui, service)


@router.get("/overrides/{override_id}/inline-form", response_class=HTMLResponse)
def winners_override_inline_form(
    request: Request,
    override_id: int,
    _: RequireStaff,
    service: Winners,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: swap an override row for its edit form."""
    return ui.page(
        request,
        "_winner_override_row_edit.html",
        _PAGE,
        override=service.get(override_id),
        seasons=service.list_seasons(),
    )


@router.post("/overrides/{override_id}/inline-edit", response_class=HTMLResponse)
def winners_override_inline_edit(  # noqa: PLR0913 — FastAPI dependencies
    request: Request,
    override_id: int,
    form: Annotated[WinnerOverrideForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    service: Winners,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: save a winner override and refresh the tables."""
    try:
        service.update(override_id, form, user.id if user else None)
    except ValidationError as exc:
        return _panel(request, ui, service, error=exc.message)
    return _panel(request, ui, service)


@router.post("/overrides/{override_id}/inline-delete", response_class=HTMLResponse)
def winners_override_inline_delete(
    request: Request,
    override_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Winners,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: delete a winner override and refresh the tables."""
    service.delete(override_id)
    return _panel(request, ui, service)
