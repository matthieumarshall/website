"""Staff-editable rich-text pages: rules and administration guides."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.export import build_document_pdf, build_rules_pdf
from website.models.forms import RichTextForm
from website.services.content import get_guide
from website.web.csrf import CsrfProtected
from website.web.deps import CurrentUserDep, Pages, RendererDep
from website.web.identity import is_staff
from website.web.security import RequireStaff

router = APIRouter()
_RULES_PAGE = "rules_and_constitution"


def _pdf(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/rules-and-constitution", response_class=HTMLResponse)
def rules_and_constitution(
    request: Request, pages: Pages, ui: RendererDep
) -> HTMLResponse:
    """Show the league rules and constitution."""
    return ui.page(
        request,
        "rules_and_constitution.html",
        _RULES_PAGE,
        content=pages.rules(),
        is_admin=is_staff(request),
    )


@router.get("/rules-and-constitution/edit", response_class=HTMLResponse)
def rules_and_constitution_edit_form(
    request: Request, _: RequireStaff, pages: Pages, ui: RendererDep
) -> HTMLResponse:
    """Staff: show the rules editor."""
    return ui.page(
        request, "rules_and_constitution_form.html", _RULES_PAGE, content=pages.rules()
    )


@router.post("/rules-and-constitution/edit")
def rules_and_constitution_edit_submit(
    form: Annotated[RichTextForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    pages: Pages,
) -> RedirectResponse:
    """Staff: save the rules."""
    pages.save_rules(form.content, user.id if user else None)
    return RedirectResponse(url="/rules-and-constitution", status_code=303)


@router.get("/rules-and-constitution/export/pdf")
def rules_and_constitution_export_pdf(pages: Pages) -> Response:
    """Download the rules as a PDF."""
    return _pdf(build_rules_pdf(pages.rules()), "oxl-league-manual.pdf")


@router.get("/administration/{slug}", response_class=HTMLResponse)
def administration_guide_page(
    slug: str, request: Request, pages: Pages, ui: RendererDep
) -> HTMLResponse:
    """Show an administration guide."""
    guide = get_guide(slug)
    return ui.page(
        request,
        "administration_guide.html",
        guide.page,
        title=guide.title,
        slug=slug,
        content=pages.content(slug),
        is_admin=is_staff(request),
    )


@router.get("/administration/{slug}/edit", response_class=HTMLResponse)
def administration_guide_edit_form(
    slug: str, request: Request, _: RequireStaff, pages: Pages, ui: RendererDep
) -> HTMLResponse:
    """Staff: show a guide's editor."""
    guide = get_guide(slug)
    return ui.page(
        request,
        "administration_guide_form.html",
        guide.page,
        title=guide.title,
        slug=slug,
        content=pages.content(slug),
    )


@router.post("/administration/{slug}/edit")
def administration_guide_edit_submit(
    slug: str,
    form: Annotated[RichTextForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    pages: Pages,
) -> RedirectResponse:
    """Staff: save a guide."""
    get_guide(slug)
    pages.save(slug, form.content, user.id if user else None)
    return RedirectResponse(url=f"/administration/{slug}", status_code=303)


@router.get("/administration/{slug}/export/pdf")
def administration_guide_export_pdf(slug: str, pages: Pages) -> Response:
    """Download a guide as a PDF."""
    guide = get_guide(slug)
    return _pdf(build_document_pdf(guide.title, pages.content(slug)), guide.filename)
