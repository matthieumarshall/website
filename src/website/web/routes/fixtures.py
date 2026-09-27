"""The fixture calendar, with HTMX editing of seasons, fixtures and images."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from website.models.forms import FixtureCopyForm, FixtureForm, SeasonForm
from website.services.fixtures import FixtureImages
from website.web.csrf import CsrfProtected
from website.web.deps import Fixtures, ImageStoreDep, RendererDep
from website.web.rendering import Renderer
from website.web.security import RequireStaff
from website.web.uploads import read_upload

router = APIRouter(prefix="/fixtures")
_PAGE = "fixtures"
_FORM = "_fixture_form.html"
_FIXTURE = "/seasons/{season_id}/fixtures/{fixture_id}"


def _season_redirect(season_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/fixtures?season_id={season_id}", status_code=302)


def _gallery(
    request: Request,
    ui: Renderer,
    gallery: FixtureImages,
    season_id: int,
    fixture_id: int,
) -> HTMLResponse:
    return ui.page(
        request,
        "_fixture_images.html",
        _PAGE,
        fixture_id=fixture_id,
        season_id=season_id,
        view=gallery,
    )


# -- public --------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def fixtures(
    request: Request, service: Fixtures, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """Show a season's fixtures (default: latest season)."""
    view = service.season_view(season_id)
    return ui.page(
        request, "fixtures.html", _PAGE, season=view.selected_season, view=view
    )


@router.get("/season-panel", response_class=HTMLResponse)
def fixtures_season_panel(
    request: Request, service: Fixtures, ui: RendererDep, season_id: int | None = None
) -> HTMLResponse:
    """HTMX: swap in another season's fixtures."""
    view = service.season_view(season_id)
    return ui.page(
        request,
        "_fixtures_season_panel.html",
        _PAGE,
        season=view.selected_season,
        view=view,
    )


@router.get("/fixture-detail", response_class=HTMLResponse)
def fixtures_fixture_detail(
    request: Request,
    fixture_id: int,
    service: Fixtures,
    ui: RendererDep,
    season_id: int | None = None,
) -> HTMLResponse:
    """HTMX: swap in a fixture's details."""
    detail = service.detail(fixture_id)
    return ui.page(
        request, "_fixture_detail.html", _PAGE, season_id=season_id, view=detail
    )


# -- staff: seasons ------------------------------------------------------------


@router.get("/seasons/new", response_class=HTMLResponse)
def fixtures_new_season_form(
    request: Request, _: RequireStaff, ui: RendererDep
) -> HTMLResponse:
    """HTMX: show the new season form."""
    return ui.page(request, "_season_form.html", _PAGE)


@router.get("/seasons/new-form-cancel", response_class=HTMLResponse)
def fixtures_new_season_form_cancel() -> HTMLResponse:
    """HTMX: clear the season form panel."""
    return HTMLResponse("")


@router.post("/seasons")
def fixtures_create_season(
    form: Annotated[SeasonForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
) -> RedirectResponse:
    """Staff: create a season."""
    return _season_redirect(service.create_season(form.name).id)


@router.post("/seasons/{season_id}/delete")
def fixtures_delete_season(
    season_id: int, _: RequireStaff, _csrf: CsrfProtected, service: Fixtures
) -> RedirectResponse:
    """Staff: delete an empty season."""
    service.delete_season(season_id)
    return RedirectResponse(url="/fixtures", status_code=302)


# -- staff: fixtures -----------------------------------------------------------


@router.get("/seasons/{season_id}/fixtures/new", response_class=HTMLResponse)
def fixtures_new_fixture_form(
    season_id: int,
    request: Request,
    _: RequireStaff,
    service: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: show the new fixture form (if the season has room)."""
    season = service.season_for_new_fixture(season_id)
    return ui.page(request, _FORM, _PAGE, season=season, fixture=None)


@router.post("/seasons/{season_id}/fixtures")
def fixtures_create_fixture(
    season_id: int,
    form: Annotated[FixtureForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
) -> RedirectResponse:
    """Staff: create a fixture."""
    service.create_fixture(season_id, form)
    return _season_redirect(season_id)


@router.get(f"{_FIXTURE}/edit", response_class=HTMLResponse)
def fixtures_edit_form(
    season_id: int,
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    service: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: show a fixture's edit form."""
    season = service.get_season(season_id)
    fixture = service.get_fixture(fixture_id)
    return ui.page(request, _FORM, _PAGE, season=season, fixture=fixture)


@router.post(f"{_FIXTURE}/edit")
def fixtures_update_fixture(
    season_id: int,
    fixture_id: int,
    form: Annotated[FixtureForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
) -> RedirectResponse:
    """Staff: save a fixture."""
    service.update_fixture(fixture_id, form)
    return _season_redirect(season_id)


@router.post(f"{_FIXTURE}/delete")
def fixtures_delete_fixture(
    season_id: int,
    fixture_id: int,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
) -> RedirectResponse:
    """Staff: delete a fixture."""
    service.delete_fixture(fixture_id)
    return _season_redirect(season_id)


@router.get(f"{_FIXTURE}/copy", response_class=HTMLResponse)
def fixtures_copy_form(
    season_id: int,
    fixture_id: int,
    request: Request,
    _: RequireStaff,
    service: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: show a new-fixture form prefilled from an existing fixture."""
    source = service.get_fixture(fixture_id)
    return ui.page(
        request,
        _FORM,
        _PAGE,
        # fixture=None means "create new"; prefill carries the source data
        fixture=None,
        prefill=source,
        season=service.season_or_none(season_id),
        seasons=service.list_seasons(),
        copy_mode=True,
    )


@router.post("/copy")
def fixtures_copy_submit(
    form: Annotated[FixtureCopyForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
) -> RedirectResponse:
    """Staff: create a copy of a fixture in the chosen season."""
    service.create_fixture(form.season_id, form)
    return _season_redirect(form.season_id)


# -- staff: images ---------------------------------------------------------------


@router.post(f"{_FIXTURE}/images")
async def fixture_upload_image(
    season_id: int,
    fixture_id: int,
    request: Request,
    file: UploadFile,
    _: RequireStaff,
    _csrf: CsrfProtected,
    store: ImageStoreDep,
    service: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: upload a course map or photo and refresh the gallery."""
    gallery = service.add_image(fixture_id, await read_upload(file, store))
    return _gallery(request, ui, gallery, season_id, fixture_id)


@router.post(f"{_FIXTURE}/images/{{image_id}}/delete")
async def fixture_delete_image(
    season_id: int,
    fixture_id: int,
    image_id: int,
    request: Request,
    _: RequireStaff,
    _csrf: CsrfProtected,
    service: Fixtures,
    ui: RendererDep,
) -> HTMLResponse:
    """HTMX: delete an image and refresh the gallery."""
    gallery = service.delete_image(fixture_id, image_id)
    return _gallery(request, ui, gallery, season_id, fixture_id)
