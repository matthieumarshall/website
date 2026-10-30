"""Staff routes for managing Tempo Events / RaceTec results synchronization."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from website.web.csrf import CsrfProtected
from website.web.deps import Fixtures, RendererDep, ResultsSync
from website.web.security import RequireStaff

router = APIRouter(prefix="/fixtures", tags=["fixtures-sync"])
_PAGE = "fixtures"
_SYNC_TEMPLATE = "_fixture_results_sync.html"


@router.get("/{fixture_id}/sync-panel", response_class=HTMLResponse)
def fixture_sync_panel(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    fixtures_svc: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """Return the sync status card / panel for a fixture."""
    fixture = fixtures_svc.get_fixture(fixture_id)
    return ui.page(
        request,
        _SYNC_TEMPLATE,
        _PAGE,
        fixture=fixture,
    )


@router.post("/{fixture_id}/sync", response_class=HTMLResponse)
async def fixture_sync_now(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    fixtures_svc: Fixtures,
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
        sync_summary=summary,
    )


@router.post("/{fixture_id}/sync-settings", response_class=HTMLResponse)
def fixture_sync_settings(
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    sync_svc: ResultsSync,
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
        settings_updated=True,
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
        sync_summary=summary,
    )
