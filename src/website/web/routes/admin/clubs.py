"""Admin: the club list and club create/edit forms."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.errors import ConflictError, ValidationError
from website.models import Club
from website.models.forms import AdminClubCreateForm, ClubForm
from website.web.csrf import CsrfProtected
from website.web.deps import Clubs, RendererDep
from website.web.rendering import Renderer
from website.web.security import RequireStaff

router = APIRouter(prefix="/admin/clubs")
_PAGE = "admin_clubs"
_FORM = "admin/clubs/form.html"
_LIST_URL = "/admin/clubs"


def _form(
    request: Request, ui: Renderer, club: Club | None, error: str, status_code: int
) -> HTMLResponse:
    return ui.page(
        request, _FORM, _PAGE, status_code=status_code, club=club, error=error
    )


@router.get("", response_class=HTMLResponse)
def admin_clubs_list(
    request: Request, _: RequireStaff, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """List every club."""
    return ui.page(
        request,
        "admin/clubs/list.html",
        _PAGE,
        clubs=clubs.list_clubs(include_inactive=True),
    )


@router.get("/new", response_class=HTMLResponse)
def admin_clubs_new(request: Request, _: RequireStaff, ui: RendererDep) -> HTMLResponse:
    """Show the new club form."""
    return ui.page(request, _FORM, _PAGE, club=None)


@router.post("", response_class=HTMLResponse)
def admin_clubs_create(
    request: Request,
    form: Annotated[AdminClubCreateForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> Response:
    """Create a club, re-showing the form on error."""
    try:
        clubs.create(form)
    except ValidationError as exc:
        return _form(request, ui, None, exc.message, 422)
    except ConflictError as exc:
        return _form(request, ui, None, exc.message, 409)
    return RedirectResponse(_LIST_URL, status_code=303)


def _aliases_page(
    request: Request, clubs: Clubs, ui: Renderer, error: str = "", status: int = 200
) -> HTMLResponse:
    return ui.page(
        request,
        "admin/clubs/aliases.html",
        _PAGE,
        status_code=status,
        clubs=clubs.list_clubs(include_inactive=True),
        aliases=clubs.identities.aliases(),
        unresolved=clubs.identities.unresolved_names(),
        error=error,
    )


@router.get("/aliases", response_class=HTMLResponse)
def admin_club_aliases(
    request: Request, _: RequireStaff, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """Show imported names needing attention and known aliases."""
    return _aliases_page(request, clubs, ui)


@router.post("/aliases", response_class=HTMLResponse)
def admin_add_club_alias(
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
    club_id: Annotated[int, Form()],
    name: Annotated[str, Form()],
) -> Response:
    """Link an imported name to a club."""
    try:
        clubs.identities.add(club_id, name)
    except ValidationError as exc:
        return _aliases_page(request, clubs, ui, exc.message, 422)
    return RedirectResponse("/admin/clubs/aliases", status_code=303)


@router.post("/aliases/{alias_id}/delete")
def admin_delete_club_alias(
    alias_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
) -> Response:
    """Remove an alias; imported results remain unchanged."""
    clubs.identities.remove(alias_id)
    return RedirectResponse("/admin/clubs/aliases", status_code=303)


@router.get("/{club_id}", response_class=HTMLResponse)
def admin_clubs_edit(
    request: Request, club_id: int, _: RequireStaff, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """Show a club's edit form."""
    return ui.page(request, _FORM, _PAGE, club=clubs.get(club_id))


@router.post("/{club_id}", response_class=HTMLResponse)
def admin_clubs_update(
    request: Request,
    club_id: int,
    form: Annotated[ClubForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> Response:
    """Save a club, re-showing the form on error."""
    club = clubs.get(club_id)
    try:
        clubs.update(club_id, form)
    except ValidationError as exc:
        return _form(request, ui, club, exc.message, 422)
    return RedirectResponse(_LIST_URL, status_code=303)
