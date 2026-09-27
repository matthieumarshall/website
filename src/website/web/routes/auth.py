"""Sign in and sign out."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from website.models.forms import LoginForm
from website.web.csrf import CsrfProtected
from website.web.deps import Accounts, RendererDep
from website.web.identity import get_current_user, sign_in, sign_out
from website.web.rate_limit import LOGIN_RATE_LIMIT, limiter

router = APIRouter()
_DEFAULT_NEXT = "/news"


def _local_path(path: str) -> str:
    """Only allow redirects to paths on this site."""
    return path if path.startswith("/") else _DEFAULT_NEXT


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, ui: RendererDep) -> Response:
    """Show the login form, or skip it if already signed in."""
    next_path = _local_path(request.query_params.get("next", _DEFAULT_NEXT))
    if get_current_user(request):
        return RedirectResponse(url=next_path, status_code=302)
    return ui.page(request, "login.html", "login", error=None, next_path=next_path)


@router.post("/login", response_class=HTMLResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
def login_submit(
    request: Request,
    form: Annotated[LoginForm, Form()],
    _csrf: CsrfProtected,
    accounts: Accounts,
    ui: RendererDep,
) -> Response:
    """Check credentials and start a session."""
    user = accounts.authenticate(form.username, form.password)
    if user is None:
        return ui.page(
            request,
            "login.html",
            "login",
            status_code=401,
            error="Invalid username or password.",
        )
    sign_in(request, user)
    return RedirectResponse(url=_local_path(form.next_path), status_code=302)


@router.post("/logout")
def logout(request: Request, _csrf: CsrfProtected) -> RedirectResponse:
    """End the session."""
    sign_out(request)
    return RedirectResponse(url=_DEFAULT_NEXT, status_code=302)
