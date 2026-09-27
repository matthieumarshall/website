"""Static information pages, the account page and the cookie notice."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from website.richtext import safe_referer_path
from website.web.csrf import CsrfProtected
from website.web.deps import RendererDep, SettingsDep
from website.web.rendering import COOKIE_NOTICE_COOKIE
from website.web.security import RequireSignedIn

router = APIRouter()
_ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


@router.get("/")
def home() -> RedirectResponse:
    """Send visitors to the news page."""
    return RedirectResponse(url="/news", status_code=302)


@router.get("/entries", response_class=HTMLResponse)
def entries(request: Request, ui: RendererDep) -> HTMLResponse:
    """Team entries landing page (not linked from navigation)."""
    return ui.page(request, "entries.html", "entries")


@router.post("/dismiss-cookie-notice")
def dismiss_cookie_notice(
    request: Request, _csrf: CsrfProtected, settings: SettingsDep
) -> RedirectResponse:
    """Hide the cookie notice for a year and return to the previous page."""
    redirect_to = safe_referer_path(request.headers.get("referer", ""))
    response = RedirectResponse(url=redirect_to, status_code=302)
    response.set_cookie(
        COOKIE_NOTICE_COOKIE,
        "1",
        max_age=_ONE_YEAR_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return response


@router.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy(request: Request, ui: RendererDep) -> HTMLResponse:
    """Show the privacy policy."""
    return ui.page(request, "privacy.html", "privacy")


@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request, ui: RendererDep) -> HTMLResponse:
    """Show contact details."""
    return ui.page(request, "contact.html", "contact")


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, ui: RendererDep) -> HTMLResponse:
    """Show the about page."""
    return ui.page(request, "about.html", "about")


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, _: RequireSignedIn, ui: RendererDep) -> HTMLResponse:
    """Show the signed-in user's account details."""
    return ui.page(request, "account.html", "account")
