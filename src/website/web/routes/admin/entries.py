"""Admin: entry batches overview and per-season entry configuration."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from website.models.forms import EntryConfigForm
from website.web.csrf import CsrfProtected
from website.web.deps import EntryAdmin, RendererDep
from website.web.security import RequireAdmin

router = APIRouter(prefix="/admin/entries")
_PAGE = "admin"


@router.get("", response_class=HTMLResponse)
def admin_entries_overview(
    request: Request,
    _: RequireAdmin,
    service: EntryAdmin,
    ui: RendererDep,
    season_id: int | None = None,
    status: str | None = None,
) -> HTMLResponse:
    """List entry batches; HTMX filter requests get just the table body."""
    overview = service.overview(season_id, status)
    template = (
        "admin/entries/_batches_table_body.html"
        if ui.is_htmx(request)
        else "admin/entries/overview.html"
    )
    return ui.page(
        request,
        template,
        _PAGE,
        filter_season_id=season_id,
        filter_status=status,
        view=overview,
    )


@router.get("/{season_id}", response_class=HTMLResponse)
def admin_entries_season_detail(
    request: Request,
    season_id: int,
    _: RequireAdmin,
    service: EntryAdmin,
    ui: RendererDep,
) -> HTMLResponse:
    """Show a season's entry configuration and batches."""
    detail = service.season(season_id)
    return ui.page(request, "admin/entries/season_detail.html", _PAGE, view=detail)


@router.post("/{season_id}/config", response_class=HTMLResponse)
def admin_entries_config_save(
    season_id: int,
    form: Annotated[EntryConfigForm, Form()],
    _: RequireAdmin,
    _csrf: CsrfProtected,
    service: EntryAdmin,
) -> RedirectResponse:
    """Save a season's entry settings and prices."""
    service.save_config(season_id, form)
    return RedirectResponse(f"/admin/entries/{season_id}", status_code=303)
