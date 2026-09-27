"""The public links page with in-page (HTMX) editing for staff."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from website.errors import ValidationError
from website.models.forms import LinkForm
from website.web.csrf import CsrfProtected
from website.web.deps import Links, RendererDep
from website.web.identity import is_staff
from website.web.security import RequireStaff

router = APIRouter(prefix="/links")
_PAGE = "links"
_ITEM = "_link_item.html"
_ITEM_EDIT = "_link_item_edit.html"


@router.get("", response_class=HTMLResponse)
def links(request: Request, service: Links, ui: RendererDep) -> HTMLResponse:
    """Show active links by category (staff also see inactive links)."""
    staff = is_staff(request)
    page = service.grouped(include_inactive=staff)
    return ui.page(request, "links.html", _PAGE, is_staff=staff, view=page)


@router.post("/inline-add", response_class=HTMLResponse)
def links_inline_add(
    request: Request,
    form: Annotated[LinkForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Links,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: add a link and append it to its category group (out-of-band swap)."""
    link = service.create(form, honour_active_flag=True)
    return ui.page(
        request,
        "_link_item_added.html",
        _PAGE,
        link=link,
        is_staff=True,
        category=link.category,
    )


@router.get("/{link_id}/inline-form", response_class=HTMLResponse)
def links_inline_form(
    request: Request, link_id: int, _: RequireStaff, service: Links, ui: RendererDep
) -> HTMLResponse:
    """HTMX: swap a link for its edit form."""
    return ui.page(request, _ITEM_EDIT, _PAGE, link=service.get(link_id))


@router.get("/{link_id}/inline-item", response_class=HTMLResponse)
def links_inline_item(
    request: Request, link_id: int, _: RequireStaff, service: Links, ui: RendererDep
) -> HTMLResponse:
    """HTMX: swap a link's edit form back to the link."""
    return ui.page(request, _ITEM, _PAGE, link=service.get(link_id), is_staff=True)


@router.post("/{link_id}/inline-edit", response_class=HTMLResponse)
def links_inline_edit(
    request: Request,
    link_id: int,
    form: Annotated[LinkForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Links,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: save a link; re-show the form with the error if invalid."""
    link = service.get(link_id)
    try:
        updated = service.update(link_id, form)
    except ValidationError as exc:
        return ui.page(
            request, _ITEM_EDIT, _PAGE, status_code=422, link=link, error=exc.message
        )
    return ui.page(request, _ITEM, _PAGE, link=updated, is_staff=True)


@router.post("/{link_id}/inline-toggle", response_class=HTMLResponse)
def links_inline_toggle(
    request: Request,
    link_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Links,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: show or hide a link."""
    link = service.toggle_active(link_id)
    return ui.page(request, _ITEM, _PAGE, link=link, is_staff=True)


@router.post("/{link_id}/inline-delete", response_class=HTMLResponse)
def links_inline_delete(
    link_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Links
) -> HTMLResponse:
    """HTMX: delete a link (the empty response removes it from the page)."""
    service.delete(link_id)
    return HTMLResponse(content="", status_code=200)
