"""Staff upload and removal of a fixture's licence and assessments (HTMX)."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from website.models import FixtureDocumentType
from website.services.fixture_documents import FixtureDocuments
from website.web.csrf import CsrfProtected
from website.web.deps import CurrentUserDep, FixtureDocStoreDep, RendererDep
from website.web.deps import FixtureDocuments as FixtureDocumentsDep
from website.web.rendering import Renderer
from website.web.security import RequireStaff
from website.web.uploads import read_upload

router = APIRouter(prefix="/fixtures/seasons/{season_id}/fixtures/{fixture_id}")


def _partial(
    request: Request, ui: Renderer, view: FixtureDocuments, season_id: int
) -> HTMLResponse:
    return ui.page(
        request,
        "_fixture_documents.html",
        "fixtures",
        view=view,
        season_id=season_id,
        fixture_id=view.fixture.id,
    )


@router.post("/documents")
async def fixture_upload_document(  # noqa: PLR0913 — one dependency per concern
    season_id: int,
    fixture_id: int,
    request: Request,
    doc_type: Annotated[FixtureDocumentType, Form()],
    file: UploadFile,
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    store: FixtureDocStoreDep,
    service: FixtureDocumentsDep,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: upload a licence or assessment and refresh the documents block."""
    view = service.upload(
        fixture_id,
        doc_type,
        await read_upload(file, store),
        user.id if user else None,
    )
    return _partial(request, ui, view, season_id)


@router.post("/documents/{document_id}/delete")
def fixture_delete_document(
    season_id: int,
    fixture_id: int,
    document_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: FixtureDocumentsDep,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: delete a document and refresh the documents block."""
    view = service.delete(fixture_id, document_id)
    return _partial(request, ui, view, season_id)
