"""HTTP middleware."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# 'unsafe-inline' in style-src is required for the Quill rich-text editor;
# tile.openstreetmap.org is required for embedded Leaflet maps.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "img-src 'self' data: "
    "https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
    "font-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        """Wrap *app*; send HSTS only when *hsts* (production over HTTPS)."""
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add the security headers to the downstream response."""
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        if self._hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response
