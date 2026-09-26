"""Exception handlers: domain errors to HTTP, 403 to login, rate limits."""

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, Response
from slowapi.errors import RateLimitExceeded

from website import errors
from website.web.identity import get_current_user
from website.web.rendering import Renderer

HTTP_STATUS_FOR: dict[type[errors.DomainError], int] = {
    errors.InvalidRequestError: 400,
    errors.ForbiddenError: 403,
    errors.NotFoundError: 404,
    errors.ConflictError: 409,
    errors.PayloadTooLargeError: 413,
    errors.ValidationError: 422,
    errors.OperationFailedError: 500,
    errors.UpstreamError: 502,
    errors.ServiceUnavailableError: 503,
}
_FORBIDDEN = 403


def status_for(exc: errors.DomainError) -> int:
    """Return the HTTP status code for a domain error."""
    for error_type, status in HTTP_STATUS_FOR.items():
        if isinstance(exc, error_type):
            return status
    return 500


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    """Redirect unauthenticated 403s to login; fall back to default handling."""
    assert isinstance(exc, HTTPException)  # noqa: S101  # nosec B101
    if exc.status_code == _FORBIDDEN and not get_current_user(request):
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(
            url=f"/login?next={quote(next_path, safe='/')}", status_code=302
        )
    return await http_exception_handler(request, exc)


async def _domain_error_handler(request: Request, exc: Exception) -> Response:
    """Answer a domain error exactly as the equivalent HTTPException would."""
    assert isinstance(exc, errors.DomainError)  # noqa: S101  # nosec B101
    http_exc = HTTPException(status_code=status_for(exc), detail=exc.message or None)
    return await _http_exception_handler(request, http_exc)


async def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Return the login form with a rate-limit error message instead of JSON."""
    assert isinstance(exc, RateLimitExceeded)  # noqa: S101  # nosec B101
    renderer: Renderer = request.app.state.renderer
    return renderer.page(
        request,
        "login.html",
        "login",
        status_code=429,
        error="Too many login attempts. Please wait 15 minutes before trying again.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install the website's exception handlers on *app*."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(errors.DomainError, _domain_error_handler)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
