"""Admin: the external links list and link create/edit forms."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.content import LINK_CATEGORY_LABELS
from website.errors import ValidationError
from website.models import ExternalLink
from website.models.forms import LinkForm
from website.web.csrf import CsrfProtected
from website.web.deps import Links, RendererDep
from website.web.rendering import Renderer
from website.web.security import RequireStaff

router = APIRouter(prefix="/admin/links")
_PAGE = "admin_links"
_FORM = "admin/links/form.html"
_LIST_URL = "/admin/links"


def _form(
    request: Request,
    ui: Renderer,
    link: ExternalLink | None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return ui.page(
        request,
        _FORM,
        _PAGE,
        status_code=status_code,
        link=link,
        category_labels=LINK_CATEGORY_LABELS,
        error=error,
    )


@router.get("", response_class=HTMLResponse)
def admin_links_list(
    request: Request, _: RequireStaff, service: Links, ui: RendererDep
) -> HTMLResponse:
    """List every link."""
    return ui.page(
        request,
        "admin/links/list.html",
        _PAGE,
        links=service.list_links(),
        category_labels=LINK_CATEGORY_LABELS,
    )


@router.get("/new", response_class=HTMLResponse)
def admin_links_new(request: Request, _: RequireStaff, ui: RendererDep) -> HTMLResponse:
    """Show the new link form."""
    return _form(request, ui, None)


@router.post("", response_class=HTMLResponse)
def admin_links_create(
    request: Request,
    form: Annotated[LinkForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Links,
    ui: RendererDep,
) -> Response:
    """Create a link, re-showing the form on error."""
    try:
        service.create(form)
    except ValidationError as exc:
        return _form(request, ui, None, exc.message, 422)
    return RedirectResponse(_LIST_URL, status_code=303)


@router.get("/{link_id}", response_class=HTMLResponse)
def admin_links_edit(
    request: Request, link_id: int, _: RequireStaff, service: Links, ui: RendererDep
) -> HTMLResponse:
    """Show a link's edit form."""
    return _form(request, ui, service.get(link_id))


@router.post("/{link_id}", response_class=HTMLResponse)
def admin_links_update(  # noqa: PLR0913 — FastAPI dependencies
    request: Request,
    link_id: int,
    form: Annotated[LinkForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Links,
    ui: RendererDep,
) -> Response:
    """Save a link, re-showing the form on error."""
    link = service.get(link_id)
    try:
        service.update(link_id, form)
    except ValidationError as exc:
        return _form(request, ui, link, exc.message, 422)
    return RedirectResponse(_LIST_URL, status_code=303)


@router.post("/{link_id}/toggle")
def admin_links_toggle(
    link_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Links
) -> RedirectResponse:
    """Show or hide a link."""
    service.toggle_active(link_id)
    return RedirectResponse(_LIST_URL, status_code=303)


@router.post("/{link_id}/delete")
def admin_links_delete(
    link_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Links
) -> RedirectResponse:
    """Delete a link."""
    service.delete(link_id)
    return RedirectResponse(_LIST_URL, status_code=303)
