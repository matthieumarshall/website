"""Admin: division assignments and winner overrides (form-and-redirect pages)."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.errors import ValidationError
from website.models.forms import DivisionAssignForm, WinnerOverrideForm
from website.services.divisions import DivisionService
from website.services.winners import WinnerService
from website.web.csrf import CsrfProtected
from website.web.deps import CurrentUserDep, Divisions, RendererDep, Winners
from website.web.rendering import Renderer
from website.web.security import RequireStaff

router = APIRouter(prefix="/admin")
_DIVISIONS_URL = "/admin/divisions"
_WINNERS_URL = "/admin/winners"


def _divisions_page(
    request: Request,
    ui: Renderer,
    service: DivisionService,
    error: str | None = None,
) -> HTMLResponse:
    return ui.page(
        request,
        "admin/divisions/list.html",
        "admin_divisions",
        status_code=422 if error else 200,
        assignments=service.list_assignments(),
        seasons=service.list_seasons(),
        clubs=service.list_clubs(),
        error=error,
    )


def _winners_page(
    request: Request,
    ui: Renderer,
    service: WinnerService,
    error: str | None = None,
) -> HTMLResponse:
    return ui.page(
        request,
        "admin/winners/list.html",
        "admin_winners",
        status_code=422 if error else 200,
        overrides=service.list_overrides(),
        seasons=service.list_seasons(),
        error=error,
    )


@router.get("/divisions", response_class=HTMLResponse)
def admin_divisions_list(
    request: Request, _: RequireStaff, service: Divisions, ui: RendererDep
) -> HTMLResponse:
    """List every division assignment."""
    return _divisions_page(request, ui, service)


@router.post("/divisions", response_class=HTMLResponse)
def admin_divisions_create(
    request: Request,
    form: Annotated[DivisionAssignForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Divisions,
    ui: RendererDep,
) -> Response:
    """Assign a club to a division, re-showing the list on error."""
    try:
        service.assign(form)
    except ValidationError as exc:
        return _divisions_page(request, ui, service, exc.message)
    return RedirectResponse(_DIVISIONS_URL, status_code=303)


@router.post("/divisions/{assignment_id}/delete")
def admin_divisions_delete(
    assignment_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Divisions
) -> RedirectResponse:
    """Delete a division assignment."""
    service.remove(assignment_id)
    return RedirectResponse(_DIVISIONS_URL, status_code=303)


@router.get("/winners", response_class=HTMLResponse)
def admin_winners_list(
    request: Request, _: RequireStaff, service: Winners, ui: RendererDep
) -> HTMLResponse:
    """List every winner override."""
    return _winners_page(request, ui, service)


@router.post("/winners", response_class=HTMLResponse)
def admin_winners_create(
    request: Request,
    form: Annotated[WinnerOverrideForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    service: Winners,
    ui: RendererDep,
) -> Response:
    """Create a winner override, re-showing the list on error."""
    try:
        service.create(form, user.id if user else None)
    except ValidationError as exc:
        return _winners_page(request, ui, service, exc.message)
    return RedirectResponse(_WINNERS_URL, status_code=303)


@router.post("/winners/{override_id}/toggle")
def admin_winners_toggle(
    override_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    service: Winners,
) -> RedirectResponse:
    """Activate or deactivate a winner override."""
    service.toggle_active(override_id, user.id if user else None)
    return RedirectResponse(_WINNERS_URL, status_code=303)


@router.post("/winners/{override_id}/delete")
def admin_winners_delete(
    override_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Winners
) -> RedirectResponse:
    """Delete a winner override."""
    service.delete(override_id)
    return RedirectResponse(_WINNERS_URL, status_code=303)
