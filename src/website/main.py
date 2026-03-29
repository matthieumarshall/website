import os
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb
import nh3
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from website.auth import verify_password
from website.database import get_db, run_migrations
from website.models import UserRole
from website import repository

_IS_PRODUCTION = os.environ.get("PRODUCTION", "false").lower() == "true"

_secret_key = os.environ.get("SECRET_KEY", "")
if _IS_PRODUCTION and not _secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set in production")
if not _secret_key:
    _secret_key = "dev-only-insecure-key-do-not-use-in-prod"  # nosec B105

_UPLOADS_DIR = Path("data/uploads")
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

# Allowed HTML tags / attributes for sanitised post content
_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "img",
}
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height"},
}


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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
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
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    run_migrations(con)
    app.state.db = con
    yield
    con.close()


app = FastAPI(lifespan=_lifespan)

app.add_middleware(
    SessionMiddleware,  # type: ignore[arg-type]
    secret_key=_secret_key,
    https_only=_IS_PRODUCTION,
    same_site="lax",
)
app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]

# Ensure the uploads directory exists before mounting as a static-files endpoint.
# (StaticFiles raises at import time if the directory is absent, which happens
# before the lifespan startup handler gets a chance to create it.)
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SIDEBAR_ITEMS: list[dict[str, str]] = [
    {"name": "Home / News", "route": "/news", "page": "news"},
    {"name": "Results", "route": "/results", "page": "results"},
    {"name": "Entries", "route": "/entries", "page": "entries"},
    {
        "name": "Rules and Constitution",
        "route": "/rules-and-constitution",
        "page": "rules_and_constitution",
    },
    {"name": "Administration", "route": "/administration", "page": "administration"},
    {"name": "Fixtures", "route": "/fixtures", "page": "fixtures"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_csrf_token(request: Request) -> str:
    token: str | None = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


def _validate_csrf(request: Request, form_token: str) -> None:
    expected: str | None = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, form_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _safe_referer_path(referer: str) -> str:
    if not referer:
        return "/news"
    path = urlparse(referer).path
    return path if path and path.startswith("/") else "/news"


def get_current_user(request: Request) -> dict[str, Any] | None:
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    role = request.session.get("role")
    if user_id and username and role:
        return {"id": user_id, "username": username, "role": role}
    return None


def _page_context(request: Request, current_page: str, **extra: Any) -> dict[str, Any]:
    return {
        "current_user": get_current_user(request),
        "current_page": current_page,
        "sidebar_items": SIDEBAR_ITEMS,
        "csrf_token": _get_csrf_token(request),
        "show_cookie_notice": not request.cookies.get("cookie_notice_dismissed"),
        **extra,
    }


def _require_role(request: Request, *roles: str) -> dict[str, Any]:
    """Return the current user if they have one of the required roles, else raise."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


def _can_edit_post(user: dict[str, Any] | None, post_author_id: int) -> bool:
    """Return True if the user may edit/delete the given post."""
    if not user:
        return False
    if user["role"] == UserRole.admin:
        return True
    return user["role"] == UserRole.content_creator and user["id"] == post_author_id


def _sanitise_html(raw: str) -> str:
    return nh3.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


# ---------------------------------------------------------------------------
# Static pages
# ---------------------------------------------------------------------------


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/news", status_code=302)


@app.get("/results", response_class=HTMLResponse)
def results(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "results.html", _page_context(request, "results")
    )


@app.get("/entries", response_class=HTMLResponse)
def entries(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "entries.html", _page_context(request, "entries")
    )


@app.get("/rules-and-constitution", response_class=HTMLResponse)
def rules_and_constitution(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "rules_and_constitution.html",
        _page_context(request, "rules_and_constitution"),
    )


@app.get("/administration", response_class=HTMLResponse)
def administration(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "administration.html", _page_context(request, "administration")
    )


@app.get("/fixtures", response_class=HTMLResponse)
def fixtures(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "fixtures.html", _page_context(request, "fixtures")
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    if get_current_user(request):
        return RedirectResponse(url="/news", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", _page_context(request, "login", error=None)
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    _validate_csrf(request, csrf_token)
    user = repository.get_user_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            _page_context(request, "login", error="Invalid username or password."),
            status_code=401,
        )
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role.value
    return RedirectResponse(url="/news", status_code=302)


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)) -> RedirectResponse:
    _validate_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/news", status_code=302)


@app.post("/dismiss-cookie-notice")
def dismiss_cookie_notice(
    request: Request, csrf_token: str = Form(...)
) -> RedirectResponse:
    _validate_csrf(request, csrf_token)
    redirect_to = _safe_referer_path(request.headers.get("referer", ""))
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
        request, "privacy.html", _page_context(request, "privacy")
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
        _page_context(request, "news", paginated=paginated, base_url="/news"),
    )


@app.get("/news/create", response_class=HTMLResponse)
def news_create_form(request: Request) -> HTMLResponse:
    _require_role(request, UserRole.admin, UserRole.content_creator)
    return templates.TemplateResponse(
        request,
        "post_form.html",
        _page_context(request, "news", post=None, form_action="/news/create"),
    )


@app.post("/news/create", response_class=HTMLResponse)
def news_create_submit(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    user = _require_role(request, UserRole.admin, UserRole.content_creator)
    _validate_csrf(request, csrf_token)
    safe_content = _sanitise_html(content)
    repository.create_post(db, title=title, content=safe_content, author_id=user["id"])
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
    user = get_current_user(request)
    can_edit = _can_edit_post(user, post.author_id)
    return templates.TemplateResponse(
        request,
        "post_detail.html",
        _page_context(request, "news", post=post, can_edit=can_edit),
    )


@app.get("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_form(
    post_id: int,
    request: Request,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> HTMLResponse:
    post = repository.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    user = _require_role(request, UserRole.admin, UserRole.content_creator)
    if not _can_edit_post(user, post.author_id):
        raise HTTPException(status_code=403, detail="Cannot edit another user's post")
    return templates.TemplateResponse(
        request,
        "post_form.html",
        _page_context(request, "news", post=post, form_action=f"/news/{post_id}/edit"),
    )


@app.post("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_submit(
    post_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    post = repository.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    user = _require_role(request, UserRole.admin, UserRole.content_creator)
    _validate_csrf(request, csrf_token)
    if not _can_edit_post(user, post.author_id):
        raise HTTPException(status_code=403, detail="Cannot edit another user's post")
    safe_content = _sanitise_html(content)
    repository.update_post(db, post_id=post_id, title=title, content=safe_content)
    return RedirectResponse(url=f"/news/{post_id}", status_code=302)


@app.post("/news/{post_id}/delete")
def news_delete(
    post_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> Response:
    post = repository.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    user = _require_role(request, UserRole.admin, UserRole.content_creator)
    _validate_csrf(request, csrf_token)
    if not _can_edit_post(user, post.author_id):
        raise HTTPException(status_code=403, detail="Cannot delete another user's post")
    repository.delete_post(db, post_id)
    return RedirectResponse(url="/news", status_code=302)


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------


@app.post("/uploads/image")
async def upload_image(
    request: Request,
    file: UploadFile,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
) -> JSONResponse:
    _require_role(request, UserRole.admin, UserRole.content_creator)
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
