"""Season standings pages and staff recalculation."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from website.models.forms import SeasonScopeForm
from website.web.csrf import CsrfProtected
from website.web.deps import RendererDep, Standings
from website.web.identity import is_staff
from website.web.security import RequireStaff

router = APIRouter(prefix="/standings")
_PAGE = "standings"


@router.get("", response_class=HTMLResponse)
def standings(
    request: Request, service: Standings, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """Show a season's standings categories (default: latest season)."""
    view = service.overview(season_id)
    return ui.page(
        request, "standings.html", _PAGE, is_admin=is_staff(request), view=view
    )


@router.get("/category-panel", response_class=HTMLResponse)
def standings_category_panel(
    request: Request, service: Standings, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """HTMX: swap in the category list for another season."""
    view = service.category_panel(season_id)
    return ui.page(
        request,
        "_standings_category_panel.html",
        _PAGE,
        selected_season=view.selected_season,
        categories=view.categories,
        is_admin=is_staff(request),
    )


@router.get("/table", response_class=HTMLResponse)
def standings_table(
    request: Request,
    season_id: int,
    category: str,
    service: Standings,
    ui: RendererDep,
    standings_type: str = "individual",
) -> HTMLResponse:
    """HTMX: swap in one category's standings table."""
    table = service.table(season_id, category, standings_type)
    return ui.page(request, "_standings_table.html", _PAGE, view=table)


@router.post("/recalculate")
def standings_recalculate(
    form: Annotated[SeasonScopeForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Standings,
) -> RedirectResponse:
    """Staff: recalculate a season's standings from its race results."""
    service.recalculate(form.season_id)
    return RedirectResponse(
        url=f"/standings?season_id={form.season_id}", status_code=303
    )
