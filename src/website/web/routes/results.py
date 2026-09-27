"""Public race results: browsing panels, exports and source PDFs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from website.export import build_csv, build_pdf
from website.services.results import ResultFilters
from website.web.deps import RendererDep, Results, SettingsDep

router = APIRouter(prefix="/results")
_PAGE = "results"
Filters = Annotated[ResultFilters, Depends()]


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("", response_class=HTMLResponse)
def results(
    request: Request,
    service: Results,
    ui: RendererDep,
    season_id: int | None = None,
    fixture_id: int | None = None,
    race_id: int | None = None,
) -> HTMLResponse:
    """Show results, defaulting to the latest season's first fixture and race."""
    view = service.browse(season_id, fixture_id, race_id)
    return ui.page(request, "results.html", _PAGE, view=view)


@router.get("/fixture-panel", response_class=HTMLResponse)
def results_fixture_panel(
    request: Request, service: Results, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """HTMX: swap in a season's fixtures with the first fixture selected."""
    view = service.browse(season_id)
    return ui.page(request, "_results_fixture_panel.html", _PAGE, view=view)


@router.get("/race-panel", response_class=HTMLResponse)
def results_race_panel(
    request: Request,
    fixture_id: int,
    service: Results,
    ui: RendererDep,
    season_id: int | None = None,
    race_id: int | None = None,
) -> HTMLResponse:
    """HTMX: swap in a fixture's races with one race selected."""
    panel = service.race_panel(fixture_id, race_id)
    return ui.page(
        request,
        "_results_race_panel.html",
        _PAGE,
        season_id=season_id,
        view=panel,
    )


@router.get("/race-table", response_class=HTMLResponse)
def results_race_table(
    request: Request,
    race_id: int,
    service: Results,
    ui: RendererDep,
    fixture_id: int | None = None,
    season_id: int | None = None,
) -> HTMLResponse:
    """HTMX: swap in one race's results table."""
    race, race_results = service.race_results(race_id)
    return ui.page(
        request,
        "_results_race_table.html",
        _PAGE,
        active_race=race,
        race_results=race_results,
        fixture_id=fixture_id,
        season_id=season_id,
    )


@router.get("/export/csv")
def results_export_csv(race_id: int, service: Results, filters: Filters) -> Response:
    """Download a race's (filtered) results as CSV."""
    export = service.export(race_id, filters)
    csv_text, filename = build_csv(
        export.results, export.race_name, export.fixture_title
    )
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv",
        headers=_attachment(filename),
    )


@router.get("/export/pdf")
def results_export_pdf(race_id: int, service: Results, filters: Filters) -> Response:
    """Download a race's (filtered) results as PDF."""
    export = service.export(race_id, filters)
    pdf_bytes, filename = build_pdf(
        export.results, export.race_name, export.fixture_title
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf", headers=_attachment(filename)
    )


@router.get("/source-pdf")
def results_source_pdf(
    fixture_id: int, service: Results, settings: SettingsDep
) -> FileResponse:
    """Serve the original results PDF for a fixture."""
    path = service.source_pdf_path(fixture_id, settings.results_pdf_root)
    return FileResponse(path, media_type="application/pdf", filename=path.name)
