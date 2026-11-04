"""Staff routes for race setup and manual CSV results uploads."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from website.errors import ConflictError, ValidationError
from website.services.results_import import ResultsImportSummary
from website.web.csrf import CsrfProtected
from website.web.deps import (
    Fixtures,
    RendererDep,
    Results,
    ResultsImport,
)
from website.web.security import RequireStaff

router = APIRouter(prefix="/fixtures", tags=["results-upload"])
_PAGE = "fixtures"
_FIXTURE_PANEL = "_fixture_results_panel.html"


def _csv_text(content: bytes) -> str:
    """Decode uploaded UTF-8/UTF-16 CSV data without accepting corrupt bytes."""
    try:
        if content.startswith(b"\xff\xfe"):
            return content[2:].decode("utf-16-le")
        if content.startswith(b"\xfe\xff"):
            return content[2:].decode("utf-16-be")
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        message = "The CSV file must use UTF-8 or UTF-16 encoding."
        raise ValidationError(message) from exc


def _fixture_page(
    request: Request,
    fixture_id: int,
    season_id: int | None,
    fixtures_svc: Fixtures,
    results_svc: Results,
    ui: RendererDep,
    status_code: int,
    **context: object,
) -> HTMLResponse:
    detail = fixtures_svc.detail(fixture_id)
    view = fixtures_svc.season_view(season_id or detail.fixture.season_id).model_copy(
        update={
            "active_fixture": detail.fixture,
            "images": detail.images,
            "documents": detail.documents,
        }
    )
    races = results_svc.race_panel(fixture_id).races
    return ui.page(
        request,
        "fixtures.html",
        _PAGE,
        view=view,
        races=races,
        status_code=status_code,
        **context,
    )


@router.post("/{fixture_id}/races", response_class=HTMLResponse)
def fixture_create_race(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
    import_svc: ResultsImport,
    ui: RendererDep,
    race_name: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Create a named race for manual result entry."""
    error = None
    status_code = 200
    try:
        import_svc.create_race(fixture_id, race_name)
    except (ValidationError, ConflictError) as exc:
        error = exc.message
        status_code = 409 if isinstance(exc, ConflictError) else 422

    return _fixture_page(
        request,
        fixture_id,
        None,
        fixtures_svc,
        results_svc,
        ui,
        status_code,
        race_create_error=error,
        race_name=race_name if error else "",
        race_created=error is None,
    )


@router.post("/{fixture_id}/race/{race_id}/upload-csv", response_class=HTMLResponse)
async def fixture_upload_race_csv(  # noqa: PLR0913 — route deps and form fields
    fixture_id: int,
    race_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    csv_file: UploadFile,
    fixtures_svc: Fixtures,
    results_svc: Results,
    import_svc: ResultsImport,
    ui: RendererDep,
    return_to: Annotated[str, Form()] = "fixtures",
    season_id: Annotated[int | None, Form()] = None,
) -> HTMLResponse:
    """Replace one race's results from a validated CSV upload."""
    if return_to not in {"fixtures", "results"}:
        await csv_file.close()
        raise ValidationError("Invalid upload destination.")

    summary: ResultsImportSummary | None = None
    error = None
    status_code = 200
    try:
        summary = import_svc.ingest_csv(
            fixture_id, race_id, _csv_text(await csv_file.read())
        )
    except ValidationError as exc:
        error = exc.message
        status_code = 422
    finally:
        await csv_file.close()

    response_status = 200 if error and ui.is_htmx(request) else status_code
    if return_to == "results":
        panel = results_svc.race_panel(fixture_id, race_id)
        if ui.is_htmx(request):
            return ui.page(
                request,
                "_results_race_panel.html",
                "results",
                season_id=season_id,
                view=panel,
                upload_summary=summary,
                upload_error=error,
                upload_error_race_id=race_id,
                status_code=response_status,
            )
        return ui.page(
            request,
            "results.html",
            "results",
            view=results_svc.browse(season_id, fixture_id, race_id),
            season_id=season_id,
            upload_summary=summary,
            upload_error=error,
            upload_error_race_id=race_id,
            status_code=response_status,
        )

    if ui.is_htmx(request):
        return ui.page(
            request,
            _FIXTURE_PANEL,
            _PAGE,
            fixture=fixtures_svc.get_fixture(fixture_id),
            races=results_svc.race_panel(fixture_id).races,
            upload_summary=summary,
            upload_error=error,
            upload_error_race_id=race_id,
            status_code=response_status,
        )
    return _fixture_page(
        request,
        fixture_id,
        season_id,
        fixtures_svc,
        results_svc,
        ui,
        response_status,
        upload_summary=summary,
        upload_error=error,
        upload_error_race_id=race_id,
    )
