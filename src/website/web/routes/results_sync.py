"""Staff routes for managing Tempo Events / RaceTec results synchronization."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from website.errors import ConflictError, ValidationError
from website.models.forms import ResultForm
from website.web.csrf import CsrfProtected
from website.web.deps import Fixtures, RendererDep, Results, ResultsSync
from website.web.security import RequireStaff

router = APIRouter(prefix="/fixtures", tags=["fixtures-sync"])
_PAGE = "fixtures"
_SYNC_TEMPLATE = "_fixture_results_sync.html"


def _results_redirect(
    season_id: int, fixture_id: int, race_id: int
) -> RedirectResponse:
    """Return to the selected race after a staff result change."""
    return RedirectResponse(
        url=f"/results?season_id={season_id}&fixture_id={fixture_id}&race_id={race_id}",
        status_code=303,
    )


@router.get("/{fixture_id}/sync-panel", response_class=HTMLResponse)
def fixture_sync_panel(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    fixtures_svc: Fixtures,
    results_svc: Results,
    ui: RendererDep,
) -> HTMLResponse:
    """Return the sync status card / panel for a fixture."""
    fixture = fixtures_svc.get_fixture(fixture_id)
    races = results_svc.race_panel(fixture_id).races
    return ui.page(
        request,
        _SYNC_TEMPLATE,
        _PAGE,
        fixture=fixture,
        races=races,
    )


@router.post("/{fixture_id}/sync", response_class=HTMLResponse)
async def fixture_sync_now(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
    sync_svc: ResultsSync,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: Trigger immediate on-demand results sync from configured URL."""
    summary = await sync_svc.sync_fixture_from_url(fixture_id)
    fixture = fixtures_svc.get_fixture(fixture_id)
    return ui.page(
        request,
        _SYNC_TEMPLATE,
        _PAGE,
        fixture=fixture,
        races=results_svc.race_panel(fixture_id).races,
        sync_summary=summary,
    )


@router.post("/{fixture_id}/sync-settings", response_class=HTMLResponse)
def fixture_sync_settings(  # noqa: PLR0913 — FastAPI dependencies and form fields
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    sync_svc: ResultsSync,
    results_svc: Results,
    ui: RendererDep,
    tempo_results_url: Annotated[str | None, Form()] = None,
    auto_sync_enabled: Annotated[bool, Form()] = False,
    auto_sync_hours: Annotated[int, Form()] = 24,
    auto_sync_interval_minutes: Annotated[int, Form()] = 15,
) -> HTMLResponse:
    """Staff: Update external URL, auto-sync window (max 24h) and polling interval."""
    updated_fixture = sync_svc.update_sync_settings(
        fixture_id=fixture_id,
        tempo_results_url=tempo_results_url,
        auto_sync_enabled=auto_sync_enabled,
        auto_sync_hours=auto_sync_hours,
        auto_sync_interval_minutes=auto_sync_interval_minutes,
    )
    return ui.page(
        request,
        _SYNC_TEMPLATE,
        _PAGE,
        fixture=updated_fixture,
        races=results_svc.race_panel(fixture_id).races,
        settings_updated=True,
    )


@router.post("/{fixture_id}/race/{race_id}/sync", response_class=HTMLResponse)
async def fixture_race_sync(  # noqa: PLR0913 — FastAPI dependencies and form fields
    fixture_id: int,
    race_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
    sync_svc: ResultsSync,
    ui: RendererDep,
    racetec_url: Annotated[str | None, Form()] = None,
    sync_now: Annotated[bool, Form()] = False,
    return_to_fixture: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """Staff: save a race-specific URL and optionally fetch that race."""
    sync_svc.update_race_url(fixture_id, race_id, racetec_url)
    summary = (
        await sync_svc.sync_race_from_url(fixture_id, race_id) if sync_now else None
    )
    fixture = fixtures_svc.get_fixture(fixture_id)
    if return_to_fixture:
        return ui.page(
            request,
            _SYNC_TEMPLATE,
            _PAGE,
            fixture=fixture,
            races=results_svc.race_panel(fixture_id).races,
            sync_summary=summary,
            settings_updated=not sync_now,
            race_panel_open=True,
        )
    race, _ = results_svc.race_results(race_id)
    return ui.page(
        request,
        "_race_racetec_controls.html",
        _PAGE,
        fixture=fixture,
        race=race,
        sync_summary=summary,
        settings_updated=not sync_now,
    )


@router.post("/{fixture_id}/races", response_class=HTMLResponse)
def fixture_create_race(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
    sync_svc: ResultsSync,
    ui: RendererDep,
    race_name: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Create a race and show its URL controls on the selected fixture."""
    detail = fixtures_svc.detail(fixture_id)
    error = None
    status_code = 200
    try:
        sync_svc.create_race(fixture_id, race_name)
    except (ValidationError, ConflictError) as exc:
        error = exc.message
        status_code = 409 if isinstance(exc, ConflictError) else 422

    view = fixtures_svc.season_view(detail.fixture.season_id).model_copy(
        update={
            "active_fixture": detail.fixture,
            "images": detail.images,
            "documents": detail.documents,
        }
    )
    return ui.page(
        request,
        "fixtures.html",
        _PAGE,
        view=view,
        status_code=status_code,
        races=results_svc.race_panel(fixture_id).races,
        has_results=detail.has_results,
        race_panel_open=True,
        race_create_error=error,
        race_name=race_name if error else "",
        race_created=error is None,
    )


@router.post("/{fixture_id}/upload-results-csv", response_class=HTMLResponse)
async def fixture_upload_results_csv(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    race_name: Annotated[str, Form()],
    csv_file: UploadFile,
    fixtures_svc: Fixtures,
    results_svc: Results,
    sync_svc: ResultsSync,
    ui: RendererDep,
) -> HTMLResponse:
    """Staff: Manual CSV upload fallback for a race."""
    content_bytes = await csv_file.read()
    if content_bytes[:2] == b"\xff\xfe":
        csv_text = content_bytes[2:].decode("utf-16-le", errors="replace")
    elif content_bytes[:2] == b"\xfe\xff":
        csv_text = content_bytes[2:].decode("utf-16-be", errors="replace")
    else:
        csv_text = content_bytes.decode("utf-8-sig", errors="replace")

    summary = sync_svc.ingest_csv(
        fixture_id=fixture_id,
        race_name=race_name,
        csv_content=csv_text,
    )
    fixture = fixtures_svc.get_fixture(fixture_id)
    return ui.page(
        request,
        _SYNC_TEMPLATE,
        _PAGE,
        fixture=fixture,
        races=results_svc.race_panel(fixture_id).races,
        sync_summary=summary,
    )


@router.post("/{fixture_id}/race/{race_id}/results")
def fixture_create_manual_result(
    fixture_id: int,
    race_id: int,
    form: Annotated[ResultForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
) -> RedirectResponse:
    """Add a result that remains intact when external data is refreshed."""
    fixture = fixtures_svc.get_fixture(fixture_id)
    race, _ = results_svc.race_results(race_id)
    if race.fixture_id != fixture.id:
        raise ValidationError("Race does not belong to this round")
    results_svc.create_manual_result(race_id, **form.model_dump())
    return _results_redirect(fixture.season_id, fixture_id, race_id)


@router.post("/{fixture_id}/race/{race_id}/results/{result_id}/edit")
def fixture_update_manual_result(
    fixture_id: int,
    race_id: int,
    result_id: int,
    form: Annotated[ResultForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
) -> RedirectResponse:
    """Edit and lock a result so subsequent imports cannot overwrite it."""
    fixture = fixtures_svc.get_fixture(fixture_id)
    race, _ = results_svc.race_results(race_id)
    if race.fixture_id != fixture.id:
        raise ValidationError("Race does not belong to this round")
    results_svc.update_manual_result(race_id, result_id, **form.model_dump())
    return _results_redirect(fixture.season_id, fixture_id, race_id)


@router.post("/{fixture_id}/race/{race_id}/results/{result_id}/delete")
def fixture_delete_manual_result(
    fixture_id: int,
    race_id: int,
    result_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
    results_svc: Results,
) -> RedirectResponse:
    """Delete one result from a race."""
    fixture = fixtures_svc.get_fixture(fixture_id)
    race, _ = results_svc.race_results(race_id)
    if race.fixture_id != fixture.id:
        raise ValidationError("Race does not belong to this round")
    results_svc.delete_result(race_id, result_id)
    return _results_redirect(fixture.season_id, fixture_id, race_id)
