"""Admin: club manager accounts."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.errors import ConflictError, ValidationError
from website.models.forms import ClubManagerForm
from website.web.csrf import CsrfProtected
from website.web.deps import Accounts, Clubs, RendererDep
from website.web.security import RequireAdmin

router = APIRouter(prefix="/admin/club-managers")
_PAGE = "admin_club_managers"
_LIST = "admin/club-managers/list.html"
_LIST_URL = "/admin/club-managers"


@router.get("", response_class=HTMLResponse)
def admin_club_managers_list(
    request: Request, _: RequireAdmin, accounts: Accounts, clubs: Clubs, ui: RendererDep
) -> HTMLResponse:
    """List club manager accounts."""
    return ui.page(
        request,
        _LIST,
        _PAGE,
        managers=accounts.list_club_managers(),
        clubs=clubs.list_clubs(include_inactive=True),
    )


@router.post("", response_class=HTMLResponse)
def admin_club_managers_create(
    request: Request,
    form: Annotated[ClubManagerForm, Form()],
    _: RequireAdmin,
    _csrf: CsrfProtected,
    accounts: Accounts,
    clubs: Clubs,
    ui: RendererDep,
) -> Response:
    """Create a club manager login, re-showing the list on error."""
    try:
        accounts.create_club_manager(form)
    except (ValidationError, ConflictError) as exc:
        return ui.page(
            request,
            _LIST,
            _PAGE,
            status_code=409 if isinstance(exc, ConflictError) else 422,
            managers=accounts.list_club_managers(),
            clubs=clubs.list_clubs(include_inactive=True),
            error=exc.message,
        )
    return RedirectResponse(_LIST_URL, status_code=303)


@router.post("/{manager_id}/toggle", response_class=HTMLResponse)
def admin_club_managers_toggle(
    manager_id: int, _: RequireAdmin, _csrf: CsrfProtected, accounts: Accounts
) -> RedirectResponse:
    """Activate or deactivate a club manager."""
    accounts.toggle_club_manager(manager_id)
    return RedirectResponse(_LIST_URL, status_code=303)
