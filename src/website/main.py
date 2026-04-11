import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import duckdb
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi_permissions import (
    Allow,
    All,
    Authenticated,
    configure_permissions,
    has_permission,
)
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from website.auth import verify_password
from website.database import get_db, run_migrations
from website.helpers import (
    geocode_address,
    page_context,
    parse_timetable_from_json,
    safe_referer_path,
    sanitise_html,
    validate_csrf,
)
from website.identity import get_active_principals, get_current_user
from website.models import (
    FixtureCreate,
    FixtureUpdate,
    PostCreate,
    PostResource,
    SeasonCreate,
    _MAX_FIXTURES_PER_SEASON,
)
from website import repository
from website.export import (
    build_csv,
    build_pdf,
    build_rules_pdf,
    filter_results as filter_race_results,
)

_logger = logging.getLogger(__name__)

_IS_PRODUCTION = os.environ.get("PRODUCTION", "false").lower() == "true"
_IS_TESTING = os.environ.get("TESTING", "false").lower() == "true"

_secret_key = os.environ.get("SECRET_KEY", "")
if _IS_PRODUCTION and not _secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set in production")
if not _secret_key:
    _secret_key = "dev-only-insecure-key-do-not-use-in-prod"  # nosec B105

_UPLOADS_DIR = Path("data/uploads")
_FIXTURE_MAPS_DIR = Path("data/fixture-maps")
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        # 'unsafe-inline' in style-src is required for the Quill rich-text editor
        # tile.openstreetmap.org is required for embedded Leaflet maps
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
            "font-src 'self'; "
            "frame-ancestors 'none'"
        )
        if _IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    from website.database import _get_db_path

    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _FIXTURE_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    run_migrations(con)
    app.state.db = con
    yield
    con.close()


app = FastAPI(lifespan=_lifespan)

# Rate limiter for brute-force protection
_limiter = Limiter(key_func=get_remote_address)
app.state.limiter = _limiter


# Conditional rate limit decorator that skips limiting in test mode
def _rate_limit_if_prod(rate_limit: str):
    """Rate limit decorator that only applies in production."""

    def decorator(func):
        if _IS_TESTING:
            return func
        return _limiter.limit(rate_limit)(func)

    return decorator


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Redirect unauthenticated 403s to login; fall back to default handling."""
    if exc.status_code == 403 and not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return await http_exception_handler(request, exc)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> HTMLResponse:
    """Return the login form with a rate-limit error message instead of JSON."""
    return templates.TemplateResponse(
        request,
        "login.html",
        page_context(
            request,
            "login",
            error="Too many login attempts. Please wait 15 minutes before trying again.",
        ),
        status_code=429,
    )


app.add_middleware(
    SessionMiddleware,  # type: ignore[arg-type]
    secret_key=_secret_key,
    https_only=_IS_PRODUCTION,
    same_site="lax",
)
app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]

# Ensure data directories exist before mounting as static-file endpoints.
# (StaticFiles raises at import time if the directory is absent, which happens
# before the lifespan startup handler gets a chance to create it.)
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_FIXTURE_MAPS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
app.mount(
    "/fixture-maps", StaticFiles(directory=str(_FIXTURE_MAPS_DIR)), name="fixture-maps"
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

Permission = configure_permissions(get_active_principals)

# ACL for routes only accessible to authenticated staff (admin + content_creator)
_STAFF_ACL = [
    (Allow, "role:admin", All),
    (Allow, "role:content_creator", ("create", "upload")),
]

# ACL for routes only accessible to admins
_ADMIN_ACL = [(Allow, "role:admin", All)]

# ACL for routes accessible to any authenticated user
_AUTH_ACL = [(Allow, Authenticated, "view")]


def get_post_resource(
    post_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> PostResource:
    """Dependency: fetch a post by ID and wrap in PostResource for ACL checks."""
    post = repository.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return PostResource(post)


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/news", status_code=302)


@app.get("/results", response_class=HTMLResponse)
def results(
    request: Request,
    season_id: int | None = None,
    fixture_id: int | None = None,
    race_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is None and seasons:
        season_id = seasons[0].id
    selected_season = None
    fixtures_list: list = []
    active_fixture = None
    races: list = []
    active_race = None
    race_results: list = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            fixtures_list = repository.list_fixtures_for_season(db, season_id)
    if fixture_id is None and fixtures_list:
        fixture_id = fixtures_list[0].id
    if fixture_id is not None:
        active_fixture = repository.get_fixture_by_id(db, fixture_id)
        if active_fixture:
            races = repository.list_races_for_fixture(db, fixture_id)
    if race_id is None and races:
        race_id = races[0].id
    if race_id is not None:
        active_race = repository.get_race_by_id(db, race_id)
        if active_race:
            race_results = repository.list_results_for_race(db, race_id)
    return templates.TemplateResponse(
        request,
        "results.html",
        page_context(
            request,
            "results",
            seasons=seasons,
            selected_season=selected_season,
            fixtures=fixtures_list,
            active_fixture=active_fixture,
            races=races,
            active_race=active_race,
            race_results=race_results,
        ),
    )


@app.get("/results/fixture-panel", response_class=HTMLResponse)
def results_fixture_panel(
    request: Request,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is None and seasons:
        season_id = seasons[0].id
    selected_season = None
    fixtures_list: list = []
    active_fixture = None
    races: list = []
    active_race = None
    race_results: list = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            fixtures_list = repository.list_fixtures_for_season(db, season_id)
    if fixtures_list:
        active_fixture = fixtures_list[0]
        races = repository.list_races_for_fixture(db, active_fixture.id)
    if races:
        active_race = races[0]
        race_results = repository.list_results_for_race(db, active_race.id)
    return templates.TemplateResponse(
        request,
        "_results_fixture_panel.html",
        page_context(
            request,
            "results",
            selected_season=selected_season,
            fixtures=fixtures_list,
            active_fixture=active_fixture,
            races=races,
            active_race=active_race,
            race_results=race_results,
        ),
    )


@app.get("/results/race-panel", response_class=HTMLResponse)
def results_race_panel(
    request: Request,
    fixture_id: int,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    active_fixture = repository.get_fixture_by_id(db, fixture_id)
    if active_fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    races = repository.list_races_for_fixture(db, fixture_id)
    active_race = races[0] if races else None
    race_results = (
        repository.list_results_for_race(db, active_race.id) if active_race else []
    )
    return templates.TemplateResponse(
        request,
        "_results_race_panel.html",
        page_context(
            request,
            "results",
            active_fixture=active_fixture,
            season_id=season_id,
            races=races,
            active_race=active_race,
            race_results=race_results,
        ),
    )


@app.get("/results/race-table", response_class=HTMLResponse)
def results_race_table(
    request: Request,
    race_id: int,
    fixture_id: int | None = None,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    active_race = repository.get_race_by_id(db, race_id)
    if active_race is None:
        raise HTTPException(status_code=404, detail="Race not found")
    race_results = repository.list_results_for_race(db, race_id)
    return templates.TemplateResponse(
        request,
        "_results_race_table.html",
        page_context(
            request,
            "results",
            active_race=active_race,
            race_results=race_results,
            fixture_id=fixture_id,
            season_id=season_id,
        ),
    )


@app.get("/results/export/csv")
def results_export_csv(
    race_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    category: str | None = None,
    club: str | None = None,
    gender: str | None = None,
    name: str | None = None,
) -> StreamingResponse:
    race = repository.get_race_by_id(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Race not found")
    fixture = repository.get_fixture_by_id(db, race.fixture_id)
    fixture_title = fixture.title if fixture else "Unknown"
    all_results = repository.list_results_for_race(db, race_id)
    filtered = filter_race_results(
        all_results, category=category, club=club, gender=gender, name=name
    )
    csv_str, filename = build_csv(filtered, race.name, fixture_title)

    def _iter():
        yield csv_str.encode("utf-8")

    return StreamingResponse(
        _iter(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/results/export/pdf")
def results_export_pdf(
    race_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    category: str | None = None,
    club: str | None = None,
    gender: str | None = None,
    name: str | None = None,
) -> Response:
    race = repository.get_race_by_id(db, race_id)
    if race is None:
        raise HTTPException(status_code=404, detail="Race not found")
    fixture = repository.get_fixture_by_id(db, race.fixture_id)
    fixture_title = fixture.title if fixture else "Unknown"
    all_results = repository.list_results_for_race(db, race_id)
    filtered = filter_race_results(
        all_results, category=category, club=club, gender=gender, name=name
    )
    pdf_bytes, filename = build_pdf(filtered, race.name, fixture_title)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/entries", response_class=HTMLResponse)
def entries(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "entries.html", page_context(request, "entries")
    )


@app.get("/rules-and-constitution", response_class=HTMLResponse)
def rules_and_constitution(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    page = repository.get_static_page(db, "rules-and-constitution")
    principals = get_active_principals(request)
    is_admin = "role:admin" in principals
    return templates.TemplateResponse(
        request,
        "rules_and_constitution.html",
        page_context(
            request,
            "rules_and_constitution",
            content=page.content if page else "",
            is_admin=is_admin,
        ),
    )


@app.get("/rules-and-constitution/edit", response_class=HTMLResponse)
def rules_and_constitution_edit_form(
    request: Request,
    _: list = Permission("edit", _ADMIN_ACL),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    page = repository.get_static_page(db, "rules-and-constitution")
    return templates.TemplateResponse(
        request,
        "rules_and_constitution_form.html",
        page_context(
            request,
            "rules_and_constitution",
            content=page.content if page else "",
        ),
    )


@app.post("/rules-and-constitution/edit")
def rules_and_constitution_edit_submit(
    request: Request,
    csrf_token: str = Form(...),
    content: str = Form(...),
    _: list = Permission("edit", _ADMIN_ACL),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    user = get_current_user(request)
    author_id: int | None = user["id"] if user else None
    clean_content = sanitise_html(content)
    repository.upsert_static_page(
        db, "rules-and-constitution", clean_content, author_id
    )
    return RedirectResponse(url="/rules-and-constitution", status_code=303)


@app.get("/rules-and-constitution/export/pdf")
def rules_and_constitution_export_pdf(
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    page = repository.get_static_page(db, "rules-and-constitution")
    html_content = page.content if page else ""
    pdf_bytes = build_rules_pdf(html_content)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=oxl-league-manual.pdf"},
    )


@app.get("/administration", response_class=HTMLResponse)
def administration(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "administration.html", page_context(request, "administration")
    )


@app.get("/fixtures", response_class=HTMLResponse)
def fixtures(
    request: Request,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is None and seasons:
        season_id = seasons[0].id
    selected_season = None
    fixtures_list: list = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            fixtures_list = repository.list_fixtures_for_season(db, season_id)
    first_fixture = fixtures_list[0] if fixtures_list else None
    images = (
        repository.list_fixture_images(db, first_fixture.id) if first_fixture else []
    )
    return templates.TemplateResponse(
        request,
        "fixtures.html",
        page_context(
            request,
            "fixtures",
            seasons=seasons,
            selected_season=selected_season,
            fixtures=fixtures_list,
            active_fixture=first_fixture,
            images=images,
        ),
    )


@app.get("/fixtures/season-panel", response_class=HTMLResponse)
def fixtures_season_panel(
    request: Request,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is None and seasons:
        season_id = seasons[0].id
    selected_season = None
    fixtures_list: list = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            fixtures_list = repository.list_fixtures_for_season(db, season_id)
    first_fixture = fixtures_list[0] if fixtures_list else None
    images = (
        repository.list_fixture_images(db, first_fixture.id) if first_fixture else []
    )
    return templates.TemplateResponse(
        request,
        "_fixtures_season_panel.html",
        page_context(
            request,
            "fixtures",
            seasons=seasons,
            selected_season=selected_season,
            fixtures=fixtures_list,
            active_fixture=first_fixture,
            images=images,
        ),
    )


@app.get("/fixtures/fixture-detail", response_class=HTMLResponse)
def fixtures_fixture_detail(
    request: Request,
    fixture_id: int,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    fixture = repository.get_fixture_by_id(db, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    images = repository.list_fixture_images(db, fixture_id)
    has_results = repository.fixture_has_results(db, fixture_id)
    return templates.TemplateResponse(
        request,
        "_fixture_detail.html",
        page_context(
            request,
            "fixtures",
            fixture=fixture,
            season_id=season_id,
            images=images,
            has_results=has_results,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures — staff CRUD
# ---------------------------------------------------------------------------

_FIXTURES_STAFF_ACL = [
    (Allow, "role:admin", All),
    (Allow, "role:content_creator", All),
]


@app.get("/fixtures/seasons/new", response_class=HTMLResponse)
def fixtures_new_season_form(
    request: Request,
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_season_form.html",
        page_context(request, "fixtures"),
    )


@app.get("/fixtures/seasons/new-form-cancel", response_class=HTMLResponse)
def fixtures_new_season_form_cancel(_request: Request) -> HTMLResponse:
    """Return an empty fragment — used by HTMX to clear the season form panel."""
    return HTMLResponse("")


@app.post("/fixtures/seasons")
def fixtures_create_season(
    request: Request,
    name: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    validated = SeasonCreate(name=name.strip())
    if not validated.name:
        raise HTTPException(status_code=422, detail="Season name cannot be empty")
    try:
        season = repository.create_season(db, validated.name)
    except Exception:
        raise HTTPException(
            status_code=409, detail="A season with that name already exists"
        )
    return RedirectResponse(url=f"/fixtures?season_id={season.id}", status_code=302)


@app.post("/fixtures/seasons/{season_id}/delete")
def fixtures_delete_season(
    season_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    try:
        repository.delete_season(db, season_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return RedirectResponse(url="/fixtures", status_code=302)


@app.get("/fixtures/seasons/{season_id}/fixtures/new", response_class=HTMLResponse)
def fixtures_new_fixture_form(
    season_id: int,
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")
    count = repository.count_fixtures_for_season(db, season_id)
    if count >= _MAX_FIXTURES_PER_SEASON:
        raise HTTPException(
            status_code=409,
            detail=f"Season already has {count} fixtures (maximum is {_MAX_FIXTURES_PER_SEASON}).",
        )
    return templates.TemplateResponse(
        request,
        "_fixture_form.html",
        page_context(request, "fixtures", season=season, fixture=None),
    )


@app.post("/fixtures/seasons/{season_id}/fixtures")
def fixtures_create_fixture(
    season_id: int,
    request: Request,
    title: str = Form(...),
    date: str = Form(...),
    location_name: str = Form(...),
    address: str = Form(...),
    timetable_json: str = Form(default="[]"),
    travel_instructions: str = Form(""),
    what3words_word1: str = Form(default=""),
    what3words_word2: str = Form(default=""),
    what3words_word3: str = Form(default=""),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    timetable = parse_timetable_from_json(timetable_json)
    validated = FixtureCreate(
        title=title.strip(),
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date
        location_name=location_name.strip(),
        address=address.strip(),
        timetable=timetable,
        travel_instructions=travel_instructions.strip(),
        what3words_word1=what3words_word1,
        what3words_word2=what3words_word2,
        what3words_word3=what3words_word3,
    )
    # Assemble what3words: either all three provided or none
    words = [
        validated.what3words_word1,
        validated.what3words_word2,
        validated.what3words_word3,
    ]
    has_any_word = any(w for w in words)
    if has_any_word and not all(words):
        raise HTTPException(
            status_code=400,
            detail="All three What3Words words must be provided together",
        )
    what3words_str = ".".join(words) if all(words) else None

    coords = geocode_address(validated.address)
    lat, lon = (coords[0], coords[1]) if coords else (None, None)
    try:
        repository.create_fixture(
            db,
            season_id=season_id,
            title=validated.title,
            date=str(validated.date),
            location_name=validated.location_name,
            address=validated.address,
            timetable=validated.timetable,
            travel_instructions=validated.travel_instructions,
            latitude=lat,
            longitude=lon,
            what3words=what3words_str,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return RedirectResponse(url=f"/fixtures?season_id={season_id}", status_code=302)


@app.get(
    "/fixtures/seasons/{season_id}/fixtures/{fixture_id}/edit",
    response_class=HTMLResponse,
)
def fixtures_edit_form(
    season_id: int,
    fixture_id: int,
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")
    fixture = repository.get_fixture_by_id(db, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return templates.TemplateResponse(
        request,
        "_fixture_form.html",
        page_context(request, "fixtures", season=season, fixture=fixture),
    )


@app.post("/fixtures/seasons/{season_id}/fixtures/{fixture_id}/edit")
def fixtures_update_fixture(
    season_id: int,
    fixture_id: int,
    request: Request,
    title: str = Form(...),
    date: str = Form(...),
    location_name: str = Form(...),
    address: str = Form(...),
    timetable_json: str = Form(default="[]"),
    travel_instructions: str = Form(""),
    what3words_word1: str = Form(default=""),
    what3words_word2: str = Form(default=""),
    what3words_word3: str = Form(default=""),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    timetable = parse_timetable_from_json(timetable_json)
    validated = FixtureUpdate(
        title=title.strip(),
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date
        location_name=location_name.strip(),
        address=address.strip(),
        timetable=timetable,
        travel_instructions=travel_instructions.strip(),
        what3words_word1=what3words_word1,
        what3words_word2=what3words_word2,
        what3words_word3=what3words_word3,
    )
    # Assemble what3words: either all three provided or none
    words = [
        validated.what3words_word1,
        validated.what3words_word2,
        validated.what3words_word3,
    ]
    has_any_word = any(w for w in words)
    if has_any_word and not all(words):
        raise HTTPException(
            status_code=400,
            detail="All three What3Words words must be provided together",
        )
    what3words_str = ".".join(words) if all(words) else None

    coords = geocode_address(validated.address)
    lat, lon = (coords[0], coords[1]) if coords else (None, None)
    result = repository.update_fixture(
        db,
        fixture_id=fixture_id,
        title=validated.title,
        date=str(validated.date),
        location_name=validated.location_name,
        address=validated.address,
        timetable=validated.timetable,
        travel_instructions=validated.travel_instructions,
        latitude=lat,
        longitude=lon,
        what3words=what3words_str,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return RedirectResponse(url=f"/fixtures?season_id={season_id}", status_code=302)


@app.post("/fixtures/seasons/{season_id}/fixtures/{fixture_id}/delete")
def fixtures_delete_fixture(
    season_id: int,
    fixture_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    repository.delete_fixture(db, fixture_id)
    return RedirectResponse(url=f"/fixtures?season_id={season_id}", status_code=302)


@app.get(
    "/fixtures/seasons/{season_id}/fixtures/{fixture_id}/copy",
    response_class=HTMLResponse,
)
def fixtures_copy_form(
    season_id: int,
    fixture_id: int,
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    fixture = repository.get_fixture_by_id(db, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    seasons = repository.list_seasons(db)
    source_season = repository.get_season_by_id(db, season_id)
    return templates.TemplateResponse(
        request,
        "_fixture_form.html",
        page_context(
            request,
            "fixtures",
            # fixture=None means "create new"; prefill carries the source data
            fixture=None,
            prefill=fixture,
            season=source_season,
            seasons=seasons,
            copy_mode=True,
        ),
    )


@app.post("/fixtures/copy")
def fixtures_copy_submit(
    request: Request,
    season_id: int = Form(...),
    title: str = Form(...),
    date: str = Form(...),
    location_name: str = Form(...),
    address: str = Form(...),
    timetable_json: str = Form(default="[]"),
    travel_instructions: str = Form(""),
    what3words_word1: str = Form(default=""),
    what3words_word2: str = Form(default=""),
    what3words_word3: str = Form(default=""),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    timetable = parse_timetable_from_json(timetable_json)
    validated = FixtureCreate(
        title=title.strip(),
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date
        location_name=location_name.strip(),
        address=address.strip(),
        timetable=timetable,
        travel_instructions=travel_instructions.strip(),
        what3words_word1=what3words_word1,
        what3words_word2=what3words_word2,
        what3words_word3=what3words_word3,
    )
    # Assemble what3words: either all three provided or none
    words = [
        validated.what3words_word1,
        validated.what3words_word2,
        validated.what3words_word3,
    ]
    has_any_word = any(w for w in words)
    if has_any_word and not all(words):
        raise HTTPException(
            status_code=400,
            detail="All three What3Words words must be provided together",
        )
    what3words_str = ".".join(words) if all(words) else None

    coords = geocode_address(validated.address)
    try:
        repository.create_fixture(
            db,
            season_id=season_id,
            title=validated.title,
            date=str(validated.date),
            location_name=validated.location_name,
            address=validated.address,
            timetable=validated.timetable,
            travel_instructions=validated.travel_instructions,
            latitude=coords[0] if coords else None,
            longitude=coords[1] if coords else None,
            what3words=what3words_str,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return RedirectResponse(url=f"/fixtures?season_id={season_id}", status_code=302)


# ---------------------------------------------------------------------------
# Fixture image uploads
# ---------------------------------------------------------------------------


@app.post("/fixtures/seasons/{season_id}/fixtures/{fixture_id}/images")
async def fixture_upload_image(
    season_id: int,
    fixture_id: int,
    request: Request,
    file: UploadFile,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    if repository.get_fixture_by_id(db, fixture_id) is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit")
    suffix = Path(file.filename or "image").suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    _FIXTURE_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    (Path(_FIXTURE_MAPS_DIR) / filename).write_bytes(data)
    repository.create_fixture_image(db, fixture_id=fixture_id, filename=filename)
    images = repository.list_fixture_images(db, fixture_id)
    return templates.TemplateResponse(
        request,
        "_fixture_images.html",
        page_context(
            request,
            "fixtures",
            fixture_id=fixture_id,
            season_id=season_id,
            images=images,
        ),
    )


@app.post(
    "/fixtures/seasons/{season_id}/fixtures/{fixture_id}/images/{image_id}/delete"
)
async def fixture_delete_image(
    season_id: int,
    fixture_id: int,
    image_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _FIXTURES_STAFF_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    filename = repository.delete_fixture_image(db, image_id)
    if filename is not None:
        filepath = Path(_FIXTURE_MAPS_DIR) / filename
        if filepath.exists():
            filepath.unlink()
    images = repository.list_fixture_images(db, fixture_id)
    return templates.TemplateResponse(
        request,
        "_fixture_images.html",
        page_context(
            request,
            "fixtures",
            fixture_id=fixture_id,
            season_id=season_id,
            images=images,
        ),
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    if get_current_user(request):
        return RedirectResponse(url="/news", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", page_context(request, "login", error=None)
    )


@app.post("/login", response_class=HTMLResponse)
@_rate_limit_if_prod("5/15minutes")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    validate_csrf(request, csrf_token)
    user = repository.get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        _logger.warning("Failed login attempt for username: %s", username)
        return templates.TemplateResponse(
            request,
            "login.html",
            page_context(request, "login", error="Invalid username or password."),
            status_code=401,
        )
    # Session fixation: clear before setting new user session data
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role.value
    return RedirectResponse(url="/news", status_code=302)


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/news", status_code=302)


@app.post("/dismiss-cookie-notice")
def dismiss_cookie_notice(
    request: Request, csrf_token: str = Form(...)
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    redirect_to = safe_referer_path(request.headers.get("referer", ""))
    response = RedirectResponse(url=redirect_to, status_code=302)
    response.set_cookie(
        "cookie_notice_dismissed",
        "1",
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=_IS_PRODUCTION,
    )
    return response


@app.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "privacy.html", page_context(request, "privacy")
    )


@app.get("/account", response_class=HTMLResponse)
def account(
    request: Request,
    _: list = Permission("view", _AUTH_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "account.html", page_context(request, "account")
    )


# ---------------------------------------------------------------------------
# News / Posts
# ---------------------------------------------------------------------------


@app.get("/news", response_class=HTMLResponse)
def news(
    request: Request,
    page: int = 1,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    page = max(1, page)
    paginated = repository.list_posts(db, page=page)
    return templates.TemplateResponse(
        request,
        "news.html",
        page_context(request, "news", paginated=paginated, base_url="/news"),
    )


@app.get("/news/create", response_class=HTMLResponse)
def news_create_form(
    request: Request,
    _: list = Permission("create", _STAFF_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "post_form.html",
        page_context(request, "news", post=None, form_action="/news/create"),
    )


@app.post("/news/create", response_class=HTMLResponse)
def news_create_submit(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("create", _STAFF_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    validated = PostCreate(title=title, content=sanitise_html(content))
    user = get_current_user(request)
    assert user is not None  # guaranteed by Permission("create") check
    repository.create_post(
        db, title=validated.title, content=validated.content, author_id=user["id"]
    )
    return RedirectResponse(url="/news", status_code=302)


@app.get("/news/{post_id}", response_class=HTMLResponse)
def news_detail(
    post_id: int,
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    post = repository.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    principals = get_active_principals(request)
    can_edit = has_permission(principals, "edit", PostResource(post))
    return templates.TemplateResponse(
        request,
        "post_detail.html",
        page_context(request, "news", post=post, can_edit=can_edit),
    )


@app.get("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_form(
    request: Request,
    post_resource: PostResource = Permission("edit", get_post_resource),
) -> HTMLResponse:
    post = post_resource.post
    return templates.TemplateResponse(
        request,
        "post_form.html",
        page_context(request, "news", post=post, form_action=f"/news/{post.id}/edit"),
    )


@app.post("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_submit(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    post_resource: PostResource = Permission("edit", get_post_resource),
) -> Response:
    validate_csrf(request, csrf_token)
    validated = PostCreate(title=title, content=sanitise_html(content))
    repository.update_post(
        db,
        post_id=post_resource.post.id,
        title=validated.title,
        content=validated.content,
    )
    return RedirectResponse(url=f"/news/{post_resource.post.id}", status_code=302)


@app.post("/news/{post_id}/delete")
def news_delete(
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    post_resource: PostResource = Permission("delete", get_post_resource),
) -> Response:
    validate_csrf(request, csrf_token)
    repository.delete_post(db, post_resource.post.id)
    return RedirectResponse(url="/news", status_code=302)


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


@app.post("/api/upload/image")
async def upload_image(
    request: Request,
    file: UploadFile,
    _: list = Permission("upload", _STAFF_ACL),
) -> JSONResponse:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 5 MB limit")
    suffix = Path(file.filename or "image").suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (Path(_UPLOADS_DIR) / filename).write_bytes(data)
    return JSONResponse({"url": f"/uploads/{filename}"})
