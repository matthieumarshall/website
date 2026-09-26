"""Administration documents: the public list and the staff manager."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from website.models.forms import AdministrationSectionForm
from website.services.administration import AdministrationService
from website.web.csrf import CsrfProtected
from website.web.deps import (
    Administration,
    CurrentUserDep,
    DocumentStoreDep,
    RendererDep,
)
from website.web.rendering import Renderer
from website.web.security import RequireStaff
from website.web.uploads import read_upload

# Registered before the guide pages so "/administration/manage" is not a slug.
router = APIRouter(prefix="/administration")
_MANAGE_PAGE = "admin_administration"
_MANAGE_TEMPLATE = "administration_manage.html"


def _manage(
    request: Request, ui: Renderer, service: AdministrationService
) -> HTMLResponse:
    return ui.page(request, _MANAGE_TEMPLATE, _MANAGE_PAGE, sections=service.sections())


@router.get("", response_class=HTMLResponse)
def administration(
    request: Request, service: Administration, ui: RendererDep
) -> HTMLResponse:
    """List administration documents by section."""
    return ui.page(
        request,
        "administration.html",
        "administration",
        administration_sections=service.sections(),
    )


@router.get("/manage", response_class=HTMLResponse)
def administration_manage(
    request: Request, _: RequireStaff, service: Administration, ui: RendererDep
) -> HTMLResponse:
    """Staff: manage sections and documents."""
    return _manage(request, ui, service)


@router.post("/manage/sections", response_class=HTMLResponse)
def administration_create_section(
    request: Request,
    form: Annotated[AdministrationSectionForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Administration,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: add a section."""
    service.create_section(form)
    return _manage(request, ui, service)


@router.post("/manage/sections/{section_id}/delete", response_class=HTMLResponse)
def administration_delete_section(
    section_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Administration,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: delete an empty section."""
    service.delete_section(section_id)
    return _manage(request, ui, service)


@router.post("/manage/sections/{section_id}/documents", response_class=HTMLResponse)
async def administration_upload_document(
    section_id: int,
    request: Request,
    display_name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    documents: DocumentStoreDep,
    service: Administration,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: upload a document into a section."""
    upload = await read_upload(file, documents)
    service.upload_document(section_id, display_name, upload, user.id if user else None)
    return _manage(request, ui, service)


@router.post("/manage/documents/{doc_id}/delete", response_class=HTMLResponse)
def administration_delete_document(
    doc_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Administration,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: delete a document and its file."""
    service.delete_document(doc_id)
    return _manage(request, ui, service)
