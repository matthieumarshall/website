"""The public member club directory with in-page (HTMX) editing for staff."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from website.errors import ValidationError
from website.models.forms import ClubForm
from website.web.csrf import CsrfProtected
from website.web.deps import Clubs, RendererDep
from website.web.identity import is_staff
from website.web.security import RequireStaff

router = APIRouter(prefix="/clubs")
_PAGE = "clubs"
_ROW = "_club_row.html"
_ROW_EDIT = "_club_row_edit.html"


@router.get("", response_class=HTMLResponse)
def public_clubs(request: Request, clubs: Clubs, ui: RendererDep) -> HTMLResponse:
    """Show active member clubs (staff also see inactive clubs)."""
    staff = is_staff(request)
    return ui.page(
        request, "clubs.html", _PAGE, clubs=clubs.list_clubs(staff), is_staff=staff
    )


@router.post("/inline-add", response_class=HTMLResponse)
def clubs_inline_add(
    request: Request,
    form: Annotated[ClubForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: add a club and return its table row."""
    club = clubs.create(form)
    return ui.page(request, _ROW, _PAGE, club=club, is_staff=True)


@router.get("/{club_id}/inline-form", response_class=HTMLResponse)
def clubs_inline_form(
    request: Request, club_id: int, _: RequireStaff, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """HTMX: swap a club's row for its edit form."""
    return ui.page(request, _ROW_EDIT, _PAGE, club=clubs.get(club_id))


@router.get("/{club_id}/inline-row", response_class=HTMLResponse)
def clubs_inline_row(
    request: Request, club_id: int, _: RequireStaff, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """HTMX: swap a club's edit form back to its row."""
    return ui.page(request, _ROW, _PAGE, club=clubs.get(club_id), is_staff=True)


@router.post("/{club_id}/inline-edit", response_class=HTMLResponse)
def clubs_inline_edit(
    request: Request,
    club_id: int,
    form: Annotated[ClubForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: save a club; re-show the form with the error if invalid."""
    club = clubs.get(club_id)
    try:
        updated = clubs.update(club_id, form)
    except ValidationError as exc:
        return ui.page(
            request, _ROW_EDIT, _PAGE, status_code=422, club=club, error=exc.message
        )
    return ui.page(request, _ROW, _PAGE, club=updated, is_staff=True)


@router.post("/{club_id}/inline-toggle", response_class=HTMLResponse)
def clubs_inline_toggle(
    request: Request,
    club_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: activate or deactivate a club."""
    club = clubs.toggle_active(club_id)
    return ui.page(request, _ROW, _PAGE, club=club, is_staff=True)
