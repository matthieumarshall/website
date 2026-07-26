import json
import logging
import mimetypes
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any, cast

import duckdb
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
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
    FileResponse,
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

from website.auth import hash_password, verify_password
from website.database import get_db, run_migrations
from website.helpers import (
    geocode_address,
    page_context,
    parse_timetable_from_json,
    safe_referer_path,
    sanitise_html,
    validate_http_url,
    validate_csrf,
)
from website.models import (
    AthleteEntryRow,
    FixtureCreate,
    FixtureUpdate,
    PostCreate,
    PostResource,
    SeasonCreate,
    UserRole,
    _MAX_FIXTURES_PER_SEASON,
)
from website import repository
from website.export import (
    build_csv,
    build_pdf,
    build_rules_pdf,
    filter_results as filter_race_results,
)
from website.identity import (
    get_active_principals,
    get_current_user,
    require_club_manager,
)
from website import payments as _payments
from website import entries as entries_module

# Ensure .js/.css files are served with correct MIME types regardless of the OS
# registry. Python's mimetypes module reads from the Windows registry and can
# return text/plain for .js, causing browsers to refuse script execution.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

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
_ADMIN_DOCS_DIR = Path("data/uploads/administration")
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_DOC_EXTENSIONS = {".pdf", ".zip", ".docx", ".xlsx", ".csv", ".txt"}
_MAX_DOC_BYTES = 20 * 1024 * 1024  # 20 MB


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
    _ADMIN_DOCS_DIR.mkdir(parents=True, exist_ok=True)
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
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(
            url=f"/login?next={quote(next_path, safe='/')}", status_code=302
        )
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
_ADMIN_DOCS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
app.mount(
    "/fixture-maps", StaticFiles(directory=str(_FIXTURE_MAPS_DIR)), name="fixture-maps"
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = json.loads
cast(dict[str, object], templates.env.globals)["STRIPE_PUBLISHABLE_KEY"] = (
    os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
)

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

_LINK_CATEGORY_LABELS = {
    "national": "National athletics organisations",
    "clubs": "Member and local clubs",
    "leagues": "Other cross-country leagues",
}

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
    race_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    active_fixture = repository.get_fixture_by_id(db, fixture_id)
    if active_fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    races = repository.list_races_for_fixture(db, fixture_id)
    # If race_id is provided, use that; otherwise default to first race
    active_race = None
    if race_id is not None:
        active_race = repository.get_race_by_id(db, race_id)
    elif races:
        active_race = races[0]
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


# Path to the results PDFs, resolved at startup to avoid repetition.
# __file__ is src/website/main.py → 3 parents up = project root.
_RESULTS_PDF_ROOT = Path(__file__).parent.parent.parent / "data" / "uploads"


@app.get("/results/source-pdf")
def results_source_pdf(
    fixture_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> FileResponse:
    """Serve the original results PDF for a fixture.

    The path is stored in the database as a value relative to the
    ``data/uploads`` directory so that no
    user-supplied path can escape that tree.
    """
    fixture = repository.get_fixture_by_id(db, fixture_id)
    if fixture is None or not fixture.source_pdf:
        raise HTTPException(status_code=404, detail="Source PDF not available")

    # Defend against path-traversal: resolve inside the known root and verify.
    safe_path = (_RESULTS_PDF_ROOT / fixture.source_pdf).resolve()
    try:
        safe_path.relative_to(_RESULTS_PDF_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Source PDF not available")  # noqa: B904

    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Source PDF not available")

    return FileResponse(
        safe_path,
        media_type="application/pdf",
        filename=safe_path.name,
    )


@app.get("/entries", response_class=HTMLResponse)
def entries(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    user: dict[str, Any] | None = Depends(get_current_user),
) -> Response:
    """Team manager landing page: list open seasons and past batches."""
    if user and user.get("role") == "admin":
        return RedirectResponse(url="/admin/entries", status_code=303)

    ctx: dict = require_club_manager(request, db)
    club_manager = ctx["club_manager"]
    seasons = repository.list_seasons(db)
    open_seasons = []
    for season in seasons:
        config = repository.get_season_entry_config(season.id, db)
        if config and config["entries_open"]:
            fixtures_remaining = entries_module.compute_fixtures_remaining(
                season.id, db
            )
            if fixtures_remaining > 0:
                # Find next fixture date
                next_row = db.execute(
                    "SELECT MIN(date) FROM fixtures WHERE season_id = ? AND date >= current_date",
                    [season.id],
                ).fetchone()
                next_fixture_date = next_row[0] if next_row and next_row[0] else None
                open_seasons.append(
                    {
                        "season": season,
                        "fixtures_remaining": fixtures_remaining,
                        "next_fixture_date": next_fixture_date,
                    }
                )
    # Past batches for this manager's club across all seasons
    my_batches: list[dict] = []
    season_map = {s.id: s.name for s in seasons}
    for season in seasons:
        for b in repository.list_entry_batches_for_season(
            db, season_id=season.id, club_id=club_manager.club_id
        ):
            b["season_name"] = season_map.get(season.id, "?")
            my_batches.append(b)
    my_batches.sort(key=lambda x: x["created_at"] or datetime(2000, 1, 1), reverse=True)
    return templates.TemplateResponse(
        request,
        "entries/season_select.html",
        page_context(
            request,
            "entries",
            club_manager=club_manager,
            open_seasons=open_seasons,
            my_batches=my_batches,
        ),
    )


@app.get("/entries/{season_id}/add", response_class=HTMLResponse)
def entries_add_athletes(
    request: Request,
    season_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> HTMLResponse:
    """Show athlete selection form for a season."""
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    config = repository.get_season_entry_config(season_id, db)
    if not config or not config["entries_open"]:
        raise HTTPException(
            status_code=403, detail="Entries are not open for this season."
        )
    fixtures_remaining = entries_module.compute_fixtures_remaining(season_id, db)
    if fixtures_remaining < 1:
        raise HTTPException(
            status_code=403, detail="No fixtures remaining for this season."
        )
    junior_pence_per_fixture: int = config.get("junior_pence_per_fixture") or 0
    adult_pence_per_fixture: int = config.get("adult_pence_per_fixture") or 0
    if not junior_pence_per_fixture and not adult_pence_per_fixture:
        raise HTTPException(
            status_code=503,
            detail="Entry prices have not been configured for this season. Please contact the league administrator.",
        )
    junior_total_pence = junior_pence_per_fixture * fixtures_remaining
    adult_total_pence = adult_pence_per_fixture * fixtures_remaining
    # Fetch athletes from EA
    # Coerce to string (EA club ID stored in clubs.ea_club_id as string)
    ea_club_id_str = _get_ea_club_id(club_manager.club_id, db)
    ea_athletes_fetched = entries_module.fetch_club_athletes(ea_club_id_str)
    reference_date_str: str = config["ea_reference_date"]
    reference_date = date.fromisoformat(str(reference_date_str))
    entered_urns = repository.get_entered_ea_urns(season_id, club_manager.club_id, db)
    athletes = []
    for a in ea_athletes_fetched:
        ea_urn: int = int(a.get("IndividualRef", 0))
        first = a.get("FirstName", "")
        last = a.get("LastName", "")
        dob_raw = a.get("DateOfBirth", None)
        dob: date | None = None
        if dob_raw:
            try:
                dob = date.fromisoformat(str(dob_raw)[:10])
            except ValueError:
                pass
        is_registered: bool = a.get("RegistrationStatus", "") == "Registered"
        age_cat = (
            entries_module.get_oxl_age_category(dob, reference_date)
            if dob
            else "Unknown"
        )
        athletes.append(
            {
                "ea_urn": ea_urn,
                "athlete_name": f"{first} {last}".strip(),
                "date_of_birth": dob,
                "ea_age_category": age_cat,
                "is_junior": entries_module.is_junior(age_cat),
                "is_registered": is_registered,
                "already_entered": ea_urn in entered_urns,
            }
        )
    athletes.sort(key=lambda x: (x["already_entered"], x["athlete_name"]))
    return templates.TemplateResponse(
        request,
        "entries/athlete_select.html",
        page_context(
            request,
            "entries",
            season=season,
            club_manager=club_manager,
            athletes=athletes,
            junior_pence_per_fixture=junior_pence_per_fixture,
            adult_pence_per_fixture=adult_pence_per_fixture,
            junior_total_pence=junior_total_pence,
            adult_total_pence=adult_total_pence,
            fixtures_remaining=fixtures_remaining,
            deadline_warning=None,
        ),
    )


@app.post("/entries/{season_id}/batch", response_class=HTMLResponse)
def entries_create_batch(
    request: Request,
    season_id: int,
    ea_urns: list[int] = Form(default=[]),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> Response:
    """Create a pending_payment entry batch from selected athlete URNs."""
    validate_csrf(request, csrf_token)
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    config = repository.get_season_entry_config(season_id, db)
    if not config or not config["entries_open"]:
        raise HTTPException(
            status_code=403, detail="Entries are not open for this season."
        )
    if not ea_urns:
        raise HTTPException(status_code=422, detail="No athletes selected.")
    fixtures_remaining = entries_module.compute_fixtures_remaining(season_id, db)
    junior_pence_per_fixture: int = config.get("junior_pence_per_fixture") or 0
    adult_pence_per_fixture: int = config.get("adult_pence_per_fixture") or 0
    # Re-validate server-side
    ea_club_id_str = _get_ea_club_id(club_manager.club_id, db)
    ea_athletes_fetched = entries_module.fetch_club_athletes(ea_club_id_str)
    athlete_by_urn = {int(a.get("IndividualRef", 0)): a for a in ea_athletes_fetched}
    entered_urns = repository.get_entered_ea_urns(season_id, club_manager.club_id, db)
    reference_date_str: str = config["ea_reference_date"]
    reference_date = date.fromisoformat(str(reference_date_str))
    athlete_rows = []
    total_pence = 0
    for urn in ea_urns:
        a = athlete_by_urn.get(urn)
        if a is None:
            raise HTTPException(
                status_code=422, detail=f"Athlete URN {urn} not found in EA."
            )
        if a.get("RegistrationStatus", "") != "Registered":
            raise HTTPException(
                status_code=422, detail=f"Athlete {urn} is not registered."
            )
        if urn in entered_urns:
            raise HTTPException(
                status_code=409, detail=f"Athlete {urn} already entered."
            )
        dob_raw = a.get("DateOfBirth", None)
        dob: date | None = None
        if dob_raw:
            try:
                dob = date.fromisoformat(str(dob_raw)[:10])
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"Invalid DOB for athlete {urn}."
                )
        if dob is None:
            raise HTTPException(
                status_code=422, detail=f"Missing DOB for athlete {urn}."
            )
        age_cat = entries_module.get_oxl_age_category(dob, reference_date)
        junior = entries_module.is_junior(age_cat)
        amount = (
            junior_pence_per_fixture if junior else adult_pence_per_fixture
        ) * fixtures_remaining
        total_pence += amount
        athlete_rows.append(
            AthleteEntryRow(
                ea_urn=urn,
                athlete_name=f"{a.get('FirstName', '')} {a.get('LastName', '')}".strip(),
                date_of_birth=dob,
                ea_age_category=age_cat,
                is_junior=junior,
                amount_pence=amount,
            )
        )
    if not entries_module.check_allocation(
        season_id=season_id,
        club_id=club_manager.club_id,
        count_to_add=len(athlete_rows),
        db=db,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your club does not have enough allocation slots for this entry. "
                "Please contact the league administrator."
            ),
        )
    batch = repository.create_entry_batch(
        db,
        season_id=season_id,
        club_id=club_manager.club_id,
        manager_user_id=ctx["user"]["id"],
        fixtures_remaining_at_entry=fixtures_remaining,
        total_pence=total_pence,
    )
    repository.create_athlete_entries(
        db,
        batch_id=batch.id,
        season_id=season_id,
        club_id=club_manager.club_id,
        athletes=athlete_rows,
    )
    return RedirectResponse(
        f"/entries/{season_id}/batch/{batch.id}/preview", status_code=303
    )


@app.get("/entries/{season_id}/batch/{batch_id}/preview", response_class=HTMLResponse)
def entries_batch_preview(
    request: Request,
    season_id: int,
    batch_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> HTMLResponse:
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    batch = repository.get_entry_batch(batch_id, db)
    if (
        batch is None
        or batch.club_id != club_manager.club_id
        or batch.season_id != season_id
    ):
        raise HTTPException(status_code=404)
    athletes = repository.get_athlete_entries_for_batch(batch_id, db)
    junior_count = sum(1 for a in athletes if a.is_junior)
    adult_count = len(athletes) - junior_count
    junior_total = sum(a.amount_pence for a in athletes if a.is_junior)
    adult_total = sum(a.amount_pence for a in athletes if not a.is_junior)
    return templates.TemplateResponse(
        request,
        "entries/batch_preview.html",
        page_context(
            request,
            "entries",
            season=season,
            batch=batch,
            athletes=athletes,
            club_name=club_manager.club_name,
            junior_count=junior_count,
            adult_count=adult_count,
            junior_total=junior_total,
            adult_total=adult_total,
            total_pence=batch.total_pence,
        ),
    )


@app.post("/entries/{season_id}/batch/{batch_id}/checkout", response_class=HTMLResponse)
async def entries_batch_checkout(
    request: Request,
    season_id: int,
    batch_id: int,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> Response:
    validate_csrf(request, csrf_token)
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    batch = repository.get_entry_batch(batch_id, db)
    if (
        batch is None
        or batch.club_id != club_manager.club_id
        or batch.season_id != season_id
    ):
        raise HTTPException(status_code=404)
    if batch.status not in ("pending_payment", "payment_failed"):
        return RedirectResponse(
            f"/entries/{season_id}/batch/{batch_id}/success", status_code=303
        )
    athletes = repository.get_athlete_entries_for_batch(batch_id, db)
    junior_athletes = [a for a in athletes if a.is_junior]
    adult_athletes = [a for a in athletes if not a.is_junior]
    manager_email = repository.get_club_manager_email(ctx["user"]["id"], db)
    base_url = str(request.base_url).rstrip("/")
    success_url = f"{base_url}/entries/{season_id}/batch/{batch_id}/success"
    cancel_url = f"{base_url}/entries/{season_id}/batch/{batch_id}/preview"
    junior_unit = junior_athletes[0].amount_pence if junior_athletes else 0
    adult_unit = adult_athletes[0].amount_pence if adult_athletes else 0
    checkout = _payments.create_checkout_session(
        batch_id=batch_id,
        junior_count=len(junior_athletes),
        junior_unit_pence=junior_unit,
        adult_count=len(adult_athletes),
        adult_unit_pence=adult_unit,
        club_name=club_manager.club_name,
        season_name=season.name,
        manager_email=manager_email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    repository.set_batch_stripe_session(
        db, batch_id=batch_id, session_id=checkout.session_id
    )
    return RedirectResponse(checkout.url, status_code=302)


@app.get("/entries/{season_id}/batch/{batch_id}/success", response_class=HTMLResponse)
def entries_batch_success(
    request: Request,
    season_id: int,
    batch_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> HTMLResponse:
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    batch = repository.get_entry_batch(batch_id, db)
    if (
        batch is None
        or batch.club_id != club_manager.club_id
        or batch.season_id != season_id
    ):
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "entries/batch_success.html",
        page_context(
            request,
            "entries",
            season=season,
            batch=batch,
            club_name=club_manager.club_name,
        ),
    )


@app.get("/entries/{season_id}/batch/{batch_id}/receipt", response_class=HTMLResponse)
def entries_batch_receipt_html(
    request: Request,
    season_id: int,
    batch_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> HTMLResponse:
    from website import receipts as _receipts_module

    club_manager = ctx["club_manager"]
    batch = repository.get_entry_batch(batch_id, db)
    if (
        batch is None
        or batch.club_id != club_manager.club_id
        or batch.season_id != season_id
    ):
        raise HTTPException(status_code=404)
    if batch.status not in ("paid", "payment_initiated"):
        raise HTTPException(
            status_code=403, detail="Receipt is only available after payment."
        )
    return HTMLResponse(content=_receipts_module.generate_html_receipt(batch_id, db))


@app.get("/entries/{season_id}/batch/{batch_id}/receipt.pdf")
def entries_batch_receipt_pdf(
    request: Request,
    season_id: int,
    batch_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> Response:
    from website import receipts as _receipts_module

    club_manager = ctx["club_manager"]
    batch = repository.get_entry_batch(batch_id, db)
    if (
        batch is None
        or batch.club_id != club_manager.club_id
        or batch.season_id != season_id
    ):
        raise HTTPException(status_code=404)
    if batch.status not in ("paid", "payment_initiated"):
        raise HTTPException(
            status_code=403, detail="Receipt is only available after payment."
        )
    pdf_bytes = _receipts_module.generate_pdf_receipt(batch_id, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=receipt-{batch_id}.pdf"},
    )


@app.get("/entries/{season_id}", response_class=HTMLResponse)
def entries_season_overview(
    request: Request,
    season_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    ctx: dict = Depends(require_club_manager),
) -> HTMLResponse:
    """Read-only view of all entered athletes for a season (all clubs)."""
    club_manager = ctx["club_manager"]
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    entries_flat = repository.list_athlete_entries_for_season(season_id, db)
    entries_by_club: dict[str, list] = {}
    for entry in entries_flat:
        club_name = entry["club_name"]
        entries_by_club.setdefault(club_name, []).append(entry)
    config = repository.get_season_entry_config(season_id, db)
    entries_open = bool(config and config["entries_open"])
    fixtures_remaining = (
        entries_module.compute_fixtures_remaining(season_id, db) if entries_open else 0
    )
    can_add_more = entries_open and fixtures_remaining > 0
    return templates.TemplateResponse(
        request,
        "entries/season_overview.html",
        page_context(
            request,
            "entries",
            season=season,
            entries_by_club=entries_by_club,
            can_add_more=can_add_more,
            club_manager=club_manager,
        ),
    )


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


@app.get("/standings", response_class=HTMLResponse)
def standings(
    request: Request,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is None and seasons:
        season_id = seasons[0].id
    selected_season = None
    categories: list[dict] = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            categories = repository.list_standing_categories(db, season_id)
    is_admin = "role:admin" in get_active_principals(request)
    return templates.TemplateResponse(
        request,
        "standings.html",
        page_context(
            request,
            "standings",
            seasons=seasons,
            selected_season=selected_season,
            categories=categories,
            is_admin=is_admin,
        ),
    )


@app.get("/standings/category-panel", response_class=HTMLResponse)
def standings_category_panel(
    request: Request,
    season_id: int | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    selected_season = None
    categories: list[dict] = []
    if season_id is not None:
        selected_season = repository.get_season_by_id(db, season_id)
        if selected_season:
            categories = repository.list_standing_categories(db, season_id)
    is_admin = "role:admin" in get_active_principals(request)
    return templates.TemplateResponse(
        request,
        "_standings_category_panel.html",
        page_context(
            request,
            "standings",
            selected_season=selected_season,
            categories=categories,
            is_admin=is_admin,
        ),
    )


def _normalize_fixture_scores_for_standings(
    rows: list[dict], fixtures: list
) -> list[dict]:
    fixture_ids = [str(f.id) for f in fixtures]
    fixture_count = len(fixtures)

    for row in rows:
        scores_by_fixture: dict[str, int] = {}
        fixture_scores_raw = row.get("fixture_scores") or {}

        if isinstance(fixture_scores_raw, str):
            try:
                fixture_scores_raw = json.loads(fixture_scores_raw)
            except json.JSONDecodeError:
                fixture_scores_raw = {}

        if isinstance(fixture_scores_raw, dict):
            for raw_key, value in fixture_scores_raw.items():
                if raw_key is None:
                    continue
                key = str(raw_key).strip()
                if key in fixture_ids:
                    scores_by_fixture[key] = value
                    continue

                normalized = key.lower()
                if normalized.startswith("r") and normalized[1:].isdigit():
                    index = int(normalized[1:]) - 1
                    if 0 <= index < fixture_count:
                        fixture_id = str(fixtures[index].id)
                        if fixture_id not in scores_by_fixture:
                            scores_by_fixture[fixture_id] = value
                    continue

                if key.isdigit():
                    if key in fixture_ids:
                        scores_by_fixture[key] = value
                        continue
                    index = int(key) - 1
                    if 0 <= index < fixture_count:
                        fixture_id = str(fixtures[index].id)
                        if fixture_id not in scores_by_fixture:
                            scores_by_fixture[fixture_id] = value

        row["scores_by_fixture"] = scores_by_fixture
    return rows


@app.get("/standings/table", response_class=HTMLResponse)
def standings_table(
    request: Request,
    season_id: int,
    category: str,
    standings_type: str = "individual",
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    """Return an HTMX partial with a standings table for one category."""
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")
    fixtures = repository.list_fixtures_for_season(db, season_id)
    if standings_type == "team":
        rows = repository.load_team_standings(db, season_id, category)
    else:
        rows = repository.load_individual_standings(db, season_id, category)

    rows = _normalize_fixture_scores_for_standings(rows, fixtures)

    return templates.TemplateResponse(
        request,
        "_standings_table.html",
        page_context(
            request,
            "standings",
            season=season,
            category=category,
            standings_type=standings_type,
            rows=rows,
            fixtures=fixtures,
        ),
    )


@app.post("/standings/recalculate")
def standings_recalculate(
    request: Request,
    season_id: int = Form(...),
    csrf_token: str = Form(...),
    _: list = Permission("edit", _ADMIN_ACL),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    """Admin: recalculate standings for a season from race results."""
    from website.standings import recalculate_standings

    validate_csrf(request, csrf_token)
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404, detail="Season not found")
    try:
        recalculate_standings(db, season_id)
    except Exception as exc:
        _logger.exception("Error recalculating standings for season %s", season_id)
        raise HTTPException(
            status_code=500,
            detail=f"Standings calculation failed: {exc}",
        )
    return RedirectResponse(url=f"/standings?season_id={season_id}", status_code=303)


@app.get("/clubs", response_class=HTMLResponse)
def public_clubs(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    """Display the public directory of active member clubs."""
    return templates.TemplateResponse(
        request,
        "clubs.html",
        page_context(request, "clubs", clubs=repository.list_public_clubs(db)),
    )


@app.get("/links", response_class=HTMLResponse)
def links(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    """Display active, administrator-managed external links."""
    categories = [
        {"key": "national", "label": "National athletics organisations"},
        {"key": "clubs", "label": "Member and local clubs"},
        {"key": "leagues", "label": "Other cross-country leagues"},
    ]
    links_by_category = {category["key"]: [] for category in categories}
    for link in repository.list_external_links(db, active_only=True):
        links_by_category[link.category].append(link)
    return templates.TemplateResponse(
        request,
        "links.html",
        page_context(
            request,
            "links",
            categories=categories,
            links_by_category=links_by_category,
        ),
    )


@app.get("/divisions", response_class=HTMLResponse)
def divisions(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    """Display current-season senior division assignments."""
    seasons = repository.list_seasons(db)
    season = seasons[0] if seasons else None
    assignments: dict[str, dict[int, list[dict[str, str | None]]]] = {
        "women": {1: [], 2: [], 3: []},
        "men": {1: [], 2: [], 3: []},
    }
    if season is not None:
        clubs_by_id = {club.id: club for club in repository.list_clubs(db)}
        for assignment in repository.list_division_assignments(db, season.id):
            club = clubs_by_id.get(assignment.club_id)
            assignments[assignment.gender][assignment.division].append(
                {
                    "name": assignment.club_name,
                    "website_url": club.website_url if club else None,
                }
            )
    return templates.TemplateResponse(
        request,
        "divisions.html",
        page_context(
            request,
            "divisions",
            season=season,
            assignments=assignments if season else {},
        ),
    )


@app.get("/winners", response_class=HTMLResponse)
def winners(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    """Display official standings winners and administrative corrections."""
    winners_by_type = {"individual": [], "team": []}
    for winner in repository.list_public_winners(db):
        winners_by_type[winner["winner_type"]].append(winner)
    return templates.TemplateResponse(
        request,
        "winners.html",
        page_context(request, "winners", winners_by_type=winners_by_type),
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
def administration(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration.html",
        page_context(
            request,
            "administration",
            administration_sections=sections,
        ),
    )


@app.get("/administration/manage", response_class=HTMLResponse)
def administration_manage(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration_manage.html",
        page_context(
            request,
            "administration",
            sections=sections,
        ),
    )


@app.post("/administration/manage/sections", response_class=HTMLResponse)
def administration_create_section(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    slug: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    slug = slug.strip().lower()
    # Validate slug: alphanumeric + hyphens only
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise HTTPException(
            status_code=400,
            detail="Slug must contain only lowercase letters, digits, and hyphens.",
        )
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    # Derive sort_order from current section count
    existing = repository.list_administration_sections(db)
    sort_order = len(existing)
    try:
        repository.create_administration_section(
            db,
            slug=slug,
            title=title,
            description=description.strip(),
            sort_order=sort_order,
        )
    except Exception:
        raise HTTPException(
            status_code=400, detail="A section with that slug already exists."
        )
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration_manage.html",
        page_context(
            request,
            "administration",
            sections=sections,
        ),
    )


@app.post(
    "/administration/manage/sections/{section_id}/delete",
    response_class=HTMLResponse,
)
def administration_delete_section(
    section_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    try:
        repository.delete_administration_section(db, section_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration_manage.html",
        page_context(
            request,
            "administration",
            sections=sections,
        ),
    )


@app.post(
    "/administration/manage/sections/{section_id}/documents",
    response_class=HTMLResponse,
)
async def administration_upload_document(
    section_id: int,
    request: Request,
    display_name: str = Form(...),
    file: UploadFile = File(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    section = repository.get_administration_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    suffix = Path(file.filename or "document").suffix.lower()
    if suffix not in _ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(_ALLOWED_DOC_EXTENSIONS)}",
        )
    data = await file.read(_MAX_DOC_BYTES + 1)
    if len(data) > _MAX_DOC_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    section_dir = _ADMIN_DOCS_DIR / section.slug
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / safe_name).write_bytes(data)
    file_type = suffix.lstrip(".").upper()
    # Sort order: one more than the current maximum in this section
    sort_order = len(section.documents)
    display_name_clean = display_name.strip()
    if not display_name_clean:
        raise HTTPException(status_code=400, detail="Display name is required.")
    repository.create_administration_document(
        db,
        section_id=section_id,
        display_name=display_name_clean,
        filename=safe_name,
        file_type=file_type,
        sort_order=sort_order,
        uploaded_by_id=getattr(get_current_user(request), "id", None),
    )
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration_manage.html",
        page_context(
            request,
            "administration",
            sections=sections,
        ),
    )


@app.post(
    "/administration/manage/documents/{doc_id}/delete",
    response_class=HTMLResponse,
)
def administration_delete_document(
    doc_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    validate_csrf(request, csrf_token)
    result = repository.delete_administration_document(db, doc_id)
    if result is not None:
        filepath = _ADMIN_DOCS_DIR / result["section_slug"] / result["filename"]
        if filepath.exists():
            filepath.unlink()
    sections = repository.list_administration_sections(db)
    return templates.TemplateResponse(
        request,
        "administration_manage.html",
        page_context(
            request,
            "administration",
            sections=sections,
        ),
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
            season=selected_season,
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
            season=selected_season,
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
    season = repository.get_season_by_id(db, fixture.season_id)
    images = repository.list_fixture_images(db, fixture_id)
    has_results = repository.fixture_has_results(db, fixture_id)
    return templates.TemplateResponse(
        request,
        "_fixture_detail.html",
        page_context(
            request,
            "fixtures",
            fixture=fixture,
            season=season,
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
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date  # ty:ignore[invalid-argument-type]
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
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date  # ty:ignore[invalid-argument-type]
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
        date=date,  # type: ignore[invalid-argument-type]  # Pydantic coerces str to date  # ty:ignore[invalid-argument-type]
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
    fixture = repository.get_fixture_by_id(db, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found")
    season = repository.get_season_by_id(db, fixture.season_id)
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
            fixture=fixture,
            season=season,
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
    fixture = repository.get_fixture_by_id(db, fixture_id)
    season = repository.get_season_by_id(db, fixture.season_id) if fixture else None
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
            fixture=fixture,
            season=season,
            fixture_id=fixture_id,
            season_id=season_id,
            images=images,
        ),
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    next_path = request.query_params.get("next", "/news")
    if not next_path.startswith("/"):
        next_path = "/news"
    if get_current_user(request):
        return RedirectResponse(url=next_path, status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        page_context(request, "login", error=None, next_path=next_path),
    )


@app.post("/login", response_class=HTMLResponse)
@_rate_limit_if_prod("5/15minutes")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/news"),
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
    if not next_path.startswith("/"):
        next_path = "/news"
    return RedirectResponse(url=next_path, status_code=302)


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


@app.get("/contact", response_class=HTMLResponse)
def contact(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "contact.html", page_context(request, "contact")
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "about.html", page_context(request, "about")
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


# ---------------------------------------------------------------------------
# Helper: look up EA club ID from club PK
# ---------------------------------------------------------------------------


def _get_ea_club_id(club_id: int, db: duckdb.DuckDBPyConnection) -> str:
    """Return the ea_club_id string for a given clubs.id."""
    club = repository.get_club_by_id(club_id, db)
    if club is None:
        raise HTTPException(status_code=500, detail="Club configuration error.")
    return club.ea_club_id


# ---------------------------------------------------------------------------
# Admin — Entries overview & pricing config
# ---------------------------------------------------------------------------


@app.get("/admin/entries", response_class=HTMLResponse)
def admin_entries_overview(
    request: Request,
    season_id: int | None = None,
    status: str | None = None,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    seasons = repository.list_seasons(db)
    if season_id is not None:
        batches = _enrich_batches(
            repository.list_entry_batches_for_season(db, season_id, status=status), db
        )
    elif status is not None:
        # Search across all seasons
        all_batches: list[dict] = []
        for season in seasons:
            all_batches.extend(
                repository.list_entry_batches_for_season(db, season.id, status=status)
            )
        batches = _enrich_batches(all_batches, db)
    else:
        all_batches = []
        for season in seasons:
            all_batches.extend(repository.list_entry_batches_for_season(db, season.id))
        batches = _enrich_batches(all_batches, db)

    # Add season name to each batch
    season_map = {s.id: s.name for s in seasons}
    for b in batches:
        b["season_name"] = season_map.get(b.get("season_id") or 0, "?")  # type: ignore[index]

    ctx = page_context(
        request,
        "admin",
        seasons=seasons,
        batches=batches,
        filter_season_id=season_id,
        filter_status=status,
    )
    if "HX-Request" in request.headers:
        return templates.TemplateResponse(
            request,
            "admin/entries/_batches_table_body.html",
            ctx,
        )
    return templates.TemplateResponse(request, "admin/entries/overview.html", ctx)


def _enrich_batches(batches: list[dict], db: duckdb.DuckDBPyConnection) -> list[dict]:
    """Attach batch_id and season_id to batch dicts returned by list_entry_batches_for_season."""
    return batches  # already has these keys from the query


@app.get("/admin/entries/{season_id}", response_class=HTMLResponse)
def admin_entries_season_detail(
    request: Request,
    season_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    config = repository.get_season_entry_config(season_id, db)
    batches = repository.list_entry_batches_for_season(db, season_id)
    return templates.TemplateResponse(
        request,
        "admin/entries/season_detail.html",
        page_context(
            request,
            "admin",
            season=season,
            config=config,
            batches=batches,
        ),
    )


@app.post("/admin/entries/{season_id}/config", response_class=HTMLResponse)
def admin_entries_config_save(
    request: Request,
    season_id: int,
    entries_open: str = Form("off"),
    ea_reference_date: str = Form(...),
    total_fixtures: int = Form(...),
    junior_pence_per_fixture_display: float = Form(0.0),
    adult_pence_per_fixture_display: float = Form(0.0),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise HTTPException(status_code=404)
    if junior_pence_per_fixture_display < 0 or adult_pence_per_fixture_display < 0:
        raise HTTPException(status_code=422, detail="Prices cannot be negative")
    open_flag = entries_open == "on"
    repository.upsert_season_entry_config(
        db,
        season_id=season_id,
        entries_open=open_flag,
        ea_reference_date=ea_reference_date,
        total_fixtures=total_fixtures,
        junior_pence_per_fixture=round(junior_pence_per_fixture_display * 100),
        adult_pence_per_fixture=round(adult_pence_per_fixture_display * 100),
    )
    return RedirectResponse(f"/admin/entries/{season_id}", status_code=303)


# ---------------------------------------------------------------------------
# Admin — Clubs
# ---------------------------------------------------------------------------


@app.get("/admin/clubs", response_class=HTMLResponse)
def admin_clubs_list(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    clubs = repository.list_clubs(db)
    return templates.TemplateResponse(
        request,
        "admin/clubs/list.html",
        page_context(request, "admin", clubs=clubs),
    )


@app.get("/admin/clubs/new", response_class=HTMLResponse)
def admin_clubs_new(
    request: Request,
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/clubs/form.html",
        page_context(request, "admin", club=None),
    )


@app.post("/admin/clubs", response_class=HTMLResponse)
def admin_clubs_create(
    request: Request,
    name: str = Form(...),
    oxl_code: str = Form(...),
    ea_club_id: str = Form(...),
    opentrack_code: str = Form(""),
    website_url: str = Form(""),
    is_oxfordshire_member: str = Form("on"),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    name = name.strip()
    oxl_code = oxl_code.strip().upper()
    ea_club_id = ea_club_id.strip()
    normalized_opentrack_code: str | None = opentrack_code.strip() or None
    website_url = website_url.strip()
    normalized_website_url: str | None = None
    if not name or not oxl_code or not ea_club_id:
        return templates.TemplateResponse(
            request,
            "admin/clubs/form.html",
            page_context(request, "admin", club=None, error="All fields are required."),
            status_code=422,
        )
    try:
        if website_url:
            normalized_website_url = validate_http_url(website_url)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/clubs/form.html",
            page_context(request, "admin", club=None, error=str(exc)),
            status_code=422,
        )
    try:
        repository.create_club(
            db,
            name=name,
            oxl_code=oxl_code,
            ea_club_id=ea_club_id,
            opentrack_code=normalized_opentrack_code,
            website_url=normalized_website_url,
            is_oxfordshire_member=is_oxfordshire_member == "on",
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "admin/clubs/form.html",
            page_context(
                request,
                "admin",
                club=None,
                error="A club with that OXL code already exists.",
            ),
            status_code=409,
        )
    return RedirectResponse("/admin/clubs", status_code=303)


@app.get("/admin/clubs/{club_id}", response_class=HTMLResponse)
def admin_clubs_edit(
    request: Request,
    club_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    club = repository.get_club_by_id(club_id, db)
    if club is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/clubs/form.html",
        page_context(request, "admin", club=club),
    )


@app.post("/admin/clubs/{club_id}", response_class=HTMLResponse)
def admin_clubs_update(
    request: Request,
    club_id: int,
    name: str = Form(...),
    oxl_code: str = Form(...),
    ea_club_id: str = Form(...),
    opentrack_code: str = Form(""),
    website_url: str = Form(""),
    is_oxfordshire_member: str = Form("off"),
    is_active: str = Form("off"),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    club = repository.get_club_by_id(club_id, db)
    if club is None:
        raise HTTPException(status_code=404)
    name = name.strip()
    oxl_code = oxl_code.strip().upper()
    ea_club_id = ea_club_id.strip()
    normalized_opentrack_code: str | None = opentrack_code.strip() or None
    website_url = website_url.strip()
    normalized_website_url: str | None = None
    active = is_active == "on"
    if not name or not oxl_code or not ea_club_id:
        return templates.TemplateResponse(
            request,
            "admin/clubs/form.html",
            page_context(request, "admin", club=club, error="All fields are required."),
            status_code=422,
        )
    try:
        if website_url:
            normalized_website_url = validate_http_url(website_url)
        repository.update_club(
            db,
            club_id=club_id,
            name=name,
            oxl_code=oxl_code,
            ea_club_id=ea_club_id,
            is_active=active,
            opentrack_code=normalized_opentrack_code,
            website_url=normalized_website_url,
            is_oxfordshire_member=is_oxfordshire_member == "on",
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/clubs/form.html",
            page_context(request, "admin", club=club, error=str(exc)),
            status_code=422,
        )
    return RedirectResponse("/admin/clubs", status_code=303)


# ---------------------------------------------------------------------------
# Admin — Public content
# ---------------------------------------------------------------------------


@app.get("/admin/links", response_class=HTMLResponse)
def admin_links_list(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/links/list.html",
        page_context(
            request,
            "admin",
            links=repository.list_external_links(db),
            category_labels=_LINK_CATEGORY_LABELS,
        ),
    )


@app.get("/admin/links/new", response_class=HTMLResponse)
def admin_links_new(
    request: Request,
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/links/form.html",
        page_context(
            request,
            "admin",
            link=None,
            category_labels=_LINK_CATEGORY_LABELS,
        ),
    )


def _link_form_context(
    request: Request,
    link: object | None,
    error: str | None = None,
) -> dict[str, object]:
    return page_context(
        request,
        "admin",
        link=link,
        category_labels=_LINK_CATEGORY_LABELS,
        error=error,
    )


@app.post("/admin/links", response_class=HTMLResponse)
def admin_links_create(
    request: Request,
    title: str = Form(...),
    url: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    sort_order: int = Form(0),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    title = title.strip()
    normalized_description: str | None = description.strip() or None
    try:
        url = validate_http_url(url)
        if not title or len(title) > 200 or category not in _LINK_CATEGORY_LABELS:
            raise ValueError("Title and a valid category are required")
        if sort_order < 0:
            raise ValueError("Display order cannot be negative")
        repository.create_external_link(
            db, title, url, category, normalized_description, sort_order
        )
    except (ValueError, duckdb.ConstraintException) as exc:
        return templates.TemplateResponse(
            request,
            "admin/links/form.html",
            _link_form_context(request, None, str(exc)),
            status_code=422,
        )
    return RedirectResponse("/admin/links", status_code=303)


@app.get("/admin/links/{link_id}", response_class=HTMLResponse)
def admin_links_edit(
    request: Request,
    link_id: int,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    link = repository.get_external_link(db, link_id)
    if link is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/links/form.html",
        _link_form_context(request, link),
    )


@app.post("/admin/links/{link_id}", response_class=HTMLResponse)
def admin_links_update(
    request: Request,
    link_id: int,
    title: str = Form(...),
    url: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    sort_order: int = Form(0),
    is_active: str = Form("off"),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    link = repository.get_external_link(db, link_id)
    if link is None:
        raise HTTPException(status_code=404)
    title = title.strip()
    normalized_description: str | None = description.strip() or None
    try:
        url = validate_http_url(url)
        if not title or len(title) > 200 or category not in _LINK_CATEGORY_LABELS:
            raise ValueError("Title and a valid category are required")
        if sort_order < 0:
            raise ValueError("Display order cannot be negative")
        repository.update_external_link(
            db,
            link_id,
            title,
            url,
            category,
            normalized_description,
            sort_order,
            is_active == "on",
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/links/form.html",
            _link_form_context(request, link, str(exc)),
            status_code=422,
        )
    return RedirectResponse("/admin/links", status_code=303)


@app.post("/admin/links/{link_id}/toggle")
def admin_links_toggle(
    request: Request,
    link_id: int,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    if repository.get_external_link(db, link_id) is None:
        raise HTTPException(status_code=404)
    repository.toggle_external_link(db, link_id)
    return RedirectResponse("/admin/links", status_code=303)


@app.get("/admin/divisions", response_class=HTMLResponse)
def admin_divisions_list(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/divisions/list.html",
        page_context(
            request,
            "admin",
            assignments=repository.list_division_assignments(db),
            seasons=repository.list_seasons(db),
            clubs=repository.list_clubs(db),
        ),
    )


@app.post("/admin/divisions", response_class=HTMLResponse)
def admin_divisions_create(
    request: Request,
    season_id: int = Form(...),
    club_id: int = Form(...),
    gender: str = Form(...),
    division: int = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    error: str | None = None
    if repository.get_season_by_id(db, season_id) is None:
        error = "Select a valid season."
    elif repository.get_club_by_id(club_id, db) is None:
        error = "Select a valid club."
    else:
        try:
            repository.create_division_assignment(
                db, season_id, club_id, gender, division
            )
        except (ValueError, duckdb.ConstraintException) as exc:
            error = str(exc)
    if error:
        return templates.TemplateResponse(
            request,
            "admin/divisions/list.html",
            page_context(
                request,
                "admin",
                assignments=repository.list_division_assignments(db),
                seasons=repository.list_seasons(db),
                clubs=repository.list_clubs(db),
                error=error,
            ),
            status_code=422,
        )
    return RedirectResponse("/admin/divisions", status_code=303)


@app.post("/admin/divisions/{assignment_id}/delete")
def admin_divisions_delete(
    request: Request,
    assignment_id: int,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    if repository.get_division_assignment(db, assignment_id) is None:
        raise HTTPException(status_code=404)
    repository.delete_division_assignment(db, assignment_id)
    return RedirectResponse("/admin/divisions", status_code=303)


@app.get("/admin/winners", response_class=HTMLResponse)
def admin_winners_list(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/winners/list.html",
        page_context(
            request,
            "admin",
            overrides=repository.list_winner_overrides(db),
            seasons=repository.list_seasons(db),
        ),
    )


@app.post("/admin/winners", response_class=HTMLResponse)
def admin_winners_create(
    request: Request,
    season_id: int = Form(...),
    winner_type: str = Form(...),
    category: str = Form(...),
    winner_name: str = Form(...),
    club: str = Form(""),
    total_score: str = Form(""),
    note: str = Form(""),
    mode: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    error: str | None = None
    current_user = get_current_user(request)
    try:
        if repository.get_season_by_id(db, season_id) is None:
            raise ValueError("Select a valid season.")
        category = category.strip()
        winner_name = winner_name.strip()
        if not category or not winner_name:
            raise ValueError("Category and winner are required.")
        score = int(total_score) if total_score.strip() else None
        if score is not None and score < 0:
            raise ValueError("Score cannot be negative.")
        repository.create_winner_override(
            db,
            season_id,
            winner_type,
            category,
            winner_name,
            club.strip() or None,
            score,
            note.strip() or None,
            mode,
            current_user["id"] if current_user else None,
        )
    except (ValueError, duckdb.ConstraintException) as exc:
        error = str(exc)
    if error:
        return templates.TemplateResponse(
            request,
            "admin/winners/list.html",
            page_context(
                request,
                "admin",
                overrides=repository.list_winner_overrides(db),
                seasons=repository.list_seasons(db),
                error=error,
            ),
            status_code=422,
        )
    return RedirectResponse("/admin/winners", status_code=303)


@app.post("/admin/winners/{override_id}/toggle")
def admin_winners_toggle(
    request: Request,
    override_id: int,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    if not any(item.id == override_id for item in repository.list_winner_overrides(db)):
        raise HTTPException(status_code=404)
    user = get_current_user(request)
    repository.toggle_winner_override(db, override_id, user["id"] if user else None)
    return RedirectResponse("/admin/winners", status_code=303)


# ---------------------------------------------------------------------------
# Admin — Club Managers
# ---------------------------------------------------------------------------


@app.get("/admin/club-managers", response_class=HTMLResponse)
def admin_club_managers_list(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> HTMLResponse:
    managers = repository.list_club_managers(db)
    clubs = repository.list_clubs(db)
    return templates.TemplateResponse(
        request,
        "admin/club-managers/list.html",
        page_context(request, "admin", managers=managers, clubs=clubs),
    )


@app.post("/admin/club-managers", response_class=HTMLResponse)
def admin_club_managers_create(
    request: Request,
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    club_id: int = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> Response:
    validate_csrf(request, csrf_token)
    username = username.strip()
    email_clean: str | None = email.strip() or None
    managers = repository.list_club_managers(db)
    clubs = repository.list_clubs(db)

    if not username or not password or not club_id:
        return templates.TemplateResponse(
            request,
            "admin/club-managers/list.html",
            page_context(
                request,
                "admin",
                managers=managers,
                clubs=clubs,
                error="Username, password, and club are required.",
            ),
            status_code=422,
        )
    if len(password) < 12:
        return templates.TemplateResponse(
            request,
            "admin/club-managers/list.html",
            page_context(
                request,
                "admin",
                managers=managers,
                clubs=clubs,
                error="Password must be at least 12 characters.",
            ),
            status_code=422,
        )
    if repository.get_club_by_id(club_id, db) is None:
        raise HTTPException(status_code=422, detail="Invalid club selected")
    try:
        new_user = repository.create_user(
            db,
            username=username,
            hashed_password=hash_password(password),
            role=UserRole.club_manager,
        )
        repository.create_club_manager(
            db, user_id=new_user.id, club_id=club_id, email=email_clean
        )
    except Exception:
        managers = repository.list_club_managers(db)
        return templates.TemplateResponse(
            request,
            "admin/club-managers/list.html",
            page_context(
                request,
                "admin",
                managers=managers,
                clubs=clubs,
                error=f"Could not create manager. Username '{username}' may already be taken.",
            ),
            status_code=409,
        )
    return RedirectResponse("/admin/club-managers", status_code=303)


@app.post("/admin/club-managers/{manager_id}/toggle", response_class=HTMLResponse)
def admin_club_managers_toggle(
    request: Request,
    manager_id: int,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
    _: list = Permission("edit", _ADMIN_ACL),
) -> RedirectResponse:
    validate_csrf(request, csrf_token)
    repository.toggle_club_manager_active(db, manager_id=manager_id)
    return RedirectResponse("/admin/club-managers", status_code=303)


# ---------------------------------------------------------------------------
# Stripe webhook (no CSRF — raw body signature verification instead)
# ---------------------------------------------------------------------------


@app.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    try:
        event = await _payments.verify_webhook(request)
    except HTTPException:
        raise

    event_type: str = event["type"]
    data_obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        session_id: str = data_obj["id"]
        payment_intent_id: str | None = data_obj.get("payment_intent")
        payment_method_types: list[str] = data_obj.get("payment_method_types", [])
        payment_method: str = (
            payment_method_types[0] if payment_method_types else "card"
        )

        batch = repository.get_entry_batch_by_stripe_session(session_id, db)
        if batch is None:
            _logger.warning("Stripe webhook: unknown session %s", session_id)
            return Response(status_code=200)

        if batch.status not in ("paid", "payment_initiated"):
            new_status = (
                "paid"
                if data_obj.get("payment_status") == "paid"
                else "payment_initiated"
            )
            repository.update_batch_status(
                db,
                batch.id,
                new_status,
                stripe_payment_intent_id=payment_intent_id,
                stripe_payment_method=payment_method,
            )
            if new_status == "paid":
                repository.assign_race_numbers(batch.id, db)

    elif event_type == "checkout.session.async_payment_succeeded":
        # BACS debit — payment arrived after initial checkout
        session_id = data_obj["id"]
        payment_intent_id = data_obj.get("payment_intent")
        batch = repository.get_entry_batch_by_stripe_session(session_id, db)
        if batch and batch.status != "paid":
            repository.update_batch_status(
                db,
                batch.id,
                "paid",
                stripe_payment_intent_id=payment_intent_id,
            )
            repository.assign_race_numbers(batch.id, db)

    elif event_type == "checkout.session.async_payment_failed":
        session_id = data_obj["id"]
        batch = repository.get_entry_batch_by_stripe_session(session_id, db)
        if batch:
            repository.update_batch_status(db, batch.id, "payment_failed")

    return Response(status_code=200)
