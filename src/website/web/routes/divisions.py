"""The public divisions page with in-page (HTMX) editing for staff."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from website.errors import ValidationError
from website.models.forms import DivisionAssignForm, DivisionMoveForm, SeasonScopeForm
from website.services.divisions import DivisionService
from website.web.csrf import CsrfProtected
from website.web.deps import Divisions, RendererDep
from website.web.identity import is_staff
from website.web.rendering import Renderer
from website.web.security import RequireStaff

router = APIRouter(prefix="/divisions")
_PAGE = "divisions"
_PANEL = "_divisions_panel.html"


def _panel(
    request: Request,
    ui: Renderer,
    service: DivisionService,
    season_id: int | None,
    *,
    staff: bool = True,
    error: str | None = None,
) -> HTMLResponse:
    view = service.view(season_id)
    return ui.page(
        request,
        _PANEL,
        _PAGE,
        status_code=422 if error else 200,
        season=view.season,
        assignments=view.assignments,
        is_staff=staff,
        error=error,
    )


@router.get("", response_class=HTMLResponse)
def divisions(
    request: Request, service: Divisions, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """Show a season's senior divisions (default: latest season)."""
    staff = is_staff(request)
    view = service.view(season_id)
    return ui.page(
        request,
        "divisions.html",
        _PAGE,
        season=view.season,
        seasons=view.seasons,
        assignments=view.assignments,
        all_clubs=service.list_clubs() if staff else [],
        is_staff=staff,
    )


@router.get("/panel", response_class=HTMLResponse)
def divisions_panel(
    request: Request, service: Divisions, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """HTMX: swap in another season's divisions."""
    return _panel(request, ui, service, season_id, staff=is_staff(request))


@router.post("/inline-assign", response_class=HTMLResponse)
def divisions_inline_assign(
    request: Request,
    form: Annotated[DivisionAssignForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Divisions,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: place a club in a division and refresh the panel."""
    try:
        service.assign(form)
    except ValidationError as exc:
        return _panel(request, ui, service, form.season_id, error=exc.message)
    return _panel(request, ui, service, form.season_id)


@router.post("/assignments/{assignment_id}/inline-delete", response_class=HTMLResponse)
def divisions_inline_delete(
    request: Request,
    assignment_id: int,
    form: Annotated[SeasonScopeForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Divisions,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: remove a club from its division and refresh the panel."""
    service.remove(assignment_id)
    return _panel(request, ui, service, form.season_id)


@router.post("/assignments/{assignment_id}/inline-move", response_class=HTMLResponse)
def divisions_inline_move(
    request: Request,
    assignment_id: int,
    form: Annotated[DivisionMoveForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Divisions,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: move a club to another division and refresh the panel."""
    try:
        service.move(assignment_id, form.division)
    except ValidationError as exc:
        return _panel(request, ui, service, form.season_id, error=exc.message)
    return _panel(request, ui, service, form.season_id)
