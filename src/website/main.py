import os
import secrets
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from website.auth import verify_password
from website.database import engine, get_db
from website.models import Base, User

# Create DB tables on startup
Base.metadata.create_all(bind=engine)

_IS_PRODUCTION = os.environ.get("PRODUCTION", "false").lower() == "true"

# In production the SECRET_KEY env var must be explicitly set; the fallback is
# intentionally weak so it is obvious if someone mistakenly uses it in prod.
_secret_key = os.environ.get("SECRET_KEY", "")
if _IS_PRODUCTION and not _secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set in production")
if not _secret_key:
    _secret_key = "dev-only-insecure-key-do-not-use-in-prod"  # nosec B105


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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self'; "
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


app = FastAPI()

# Session middleware (inner) — sets the signed session cookie
app.add_middleware(
    SessionMiddleware,  # type: ignore[arg-type]
    secret_key=_secret_key,
    https_only=_IS_PRODUCTION,
    same_site="lax",
)

# Security headers middleware (outer) — applied to all responses including errors
app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]

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


def _get_csrf_token(request: Request) -> str:
    """Return the session CSRF token, generating and storing one if absent."""
    token: str | None = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


def _validate_csrf(request: Request, form_token: str) -> None:
    """Raise 403 if the submitted CSRF token does not match the session token."""
    expected: str | None = request.session.get("csrf_token")
    if not expected or not secrets.compare_digest(expected, form_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _safe_referer_path(referer: str) -> str:
    """Return only the path portion of a referer URL to prevent open redirect."""
    if not referer:
        return "/news"
    path = urlparse(referer).path
    return path if path and path.startswith("/") else "/news"


def get_current_user(request: Request) -> dict[str, Any] | None:
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    if user_id and username:
        return {"id": user_id, "username": username}
    return None


def _page_context(request: Request, current_page: str, **extra: Any) -> dict[str, Any]:
    """Build the common template context shared by all page routes."""
    return {
        "request": request,
        "current_user": get_current_user(request),
        "current_page": current_page,
        "sidebar_items": SIDEBAR_ITEMS,
        "csrf_token": _get_csrf_token(request),
        "show_cookie_notice": not request.cookies.get("cookie_notice_dismissed"),
        **extra,
    }


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/news", status_code=302)


@app.get("/news", response_class=HTMLResponse)
def news(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("news.html", _page_context(request, "news"))


@app.get("/results", response_class=HTMLResponse)
def results(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("results.html", _page_context(request, "results"))


@app.get("/entries", response_class=HTMLResponse)
def entries(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("entries.html", _page_context(request, "entries"))


@app.get("/rules-and-constitution", response_class=HTMLResponse)
def rules_and_constitution(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "rules_and_constitution.html", _page_context(request, "rules_and_constitution")
    )


@app.get("/administration", response_class=HTMLResponse)
def administration(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "administration.html", _page_context(request, "administration")
    )


@app.get("/fixtures", response_class=HTMLResponse)
def fixtures(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "fixtures.html", _page_context(request, "fixtures")
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    if get_current_user(request):
        return RedirectResponse(url="/news", status_code=302)
    return templates.TemplateResponse(
        "login.html", _page_context(request, "login", error=None)
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    _validate_csrf(request, csrf_token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, str(user.hashed_password)):
        return templates.TemplateResponse(
            "login.html",
            _page_context(request, "login", error="Invalid username or password."),
            status_code=401,
        )

    request.session["user_id"] = user.id
    request.session["username"] = user.username
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
        max_age=60 * 60 * 24 * 365,  # 1 year
        httponly=True,
        samesite="lax",
        secure=_IS_PRODUCTION,
    )
    return response


@app.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("privacy.html", _page_context(request, "privacy"))
