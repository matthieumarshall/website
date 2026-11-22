"""Static information pages, the account page and the cookie notice."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from website.models.forms import RichTextForm
from website.richtext import safe_referer_path
from website.web.csrf import CsrfProtected
from website.web.deps import CurrentUserDep, Pages, RendererDep, SettingsDep
from website.web.identity import is_staff
from website.web.rendering import COOKIE_NOTICE_COOKIE
from website.web.security import RequireSignedIn, RequireStaff

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
def contact(request: Request, ui: RendererDep, pages: Pages) -> HTMLResponse:
    """Show contact details."""
    return _information_page(request, ui, pages, "contact", "Contact Us")


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, ui: RendererDep, pages: Pages) -> HTMLResponse:
    """Show the about page."""
    return _information_page(request, ui, pages, "about", "About Us")


def _information_content(ui: RendererDep, pages: Pages, slug: str) -> str:
    default = ui.templates.env.get_template(f"_default_{slug}.html").render()
    return pages.content_or_default(slug, default)


def _information_page(
    request: Request, ui: RendererDep, pages: Pages, slug: str, title: str
) -> HTMLResponse:
    return ui.page(
        request,
        "information.html",
        slug,
        title=title,
        slug=slug,
        content=_information_content(ui, pages, slug),
        is_admin=is_staff(request),
    )


@router.get("/about/edit", response_class=HTMLResponse)
@router.get("/contact/edit", response_class=HTMLResponse)
def information_edit(
    request: Request, _: RequireStaff, pages: Pages, ui: RendererDep
) -> HTMLResponse:
    """Show the staff editor for an information page."""
    slug = request.url.path.split("/")[1]
    title = "About Us" if slug == "about" else "Contact Us"
    return ui.page(
        request,
        "information_form.html",
        slug,
        slug=slug,
        title=title,
        content=_information_content(ui, pages, slug),
    )


@router.post("/about/edit")
@router.post("/contact/edit")
def information_save(
    request: Request,
    form: Annotated[RichTextForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    pages: Pages,
) -> RedirectResponse:
    """Sanitise and save an information page."""
    slug = request.url.path.split("/")[1]
    pages.save(slug, form.content, user.id if user else None)
    return RedirectResponse(url=f"/{slug}", status_code=303)


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, _: RequireSignedIn, ui: RendererDep) -> HTMLResponse:
    """Show the signed-in user's account details."""
    return ui.page(request, "account.html", "account")
