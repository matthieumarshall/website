"""Public health endpoint and website status display."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from website.models import UserRole
from website.models.health import Measurements
from website.services.health import HealthSampler, public_health
from website.web.deps import RendererDep
from website.web.identity import get_current_user
from website.web.rate_limit import (
    HEALTH_GLOBAL_RATE_LIMIT,
    HEALTH_RATE_LIMIT,
    STATUS_GLOBAL_RATE_LIMIT,
    STATUS_RATE_LIMIT,
    global_rate_key,
    limiter,
)

router = APIRouter()


def _snapshot(request: Request) -> Measurements | None:
    sampler: HealthSampler | None = getattr(request.app.state, "health_sampler", None)
    return sampler.snapshot() if sampler is not None else None


@router.get("/health")
@limiter.limit(HEALTH_RATE_LIMIT)
@limiter.shared_limit(
    HEALTH_GLOBAL_RATE_LIMIT, scope="health-global", key_func=global_rate_key
)
def health(request: Request) -> JSONResponse:
    """Return coarse public readiness and resource status."""
    result = public_health(_snapshot(request), time.monotonic())
    return JSONResponse(
        result.model_dump(mode="json"),
        status_code=503 if result.status == "unavailable" else 200,
        headers={"Cache-Control": "no-store"},
    )


def _status_page(request: Request, ui: RendererDep, template: str) -> HTMLResponse:
    snapshot = _snapshot(request)
    user = get_current_user(request)
    private = snapshot if user is not None and user.role == UserRole.admin else None
    response = ui.page(
        request,
        template,
        "status",
        health=public_health(snapshot, time.monotonic()),
        private=private,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return response


@router.get("/status", response_class=HTMLResponse)
@limiter.shared_limit(STATUS_RATE_LIMIT, scope="website-status")
@limiter.shared_limit(
    STATUS_GLOBAL_RATE_LIMIT, scope="status-global", key_func=global_rate_key
)
def status_page(request: Request, ui: RendererDep) -> HTMLResponse:
    """Show current public status and administrator details."""
    return _status_page(request, ui, "status.html")


@router.get("/status/summary", response_class=HTMLResponse)
@limiter.shared_limit(STATUS_RATE_LIMIT, scope="website-status")
@limiter.shared_limit(
    STATUS_GLOBAL_RATE_LIMIT, scope="status-global", key_func=global_rate_key
)
def status_summary(request: Request, ui: RendererDep) -> HTMLResponse:
    """Refresh the current status fragment."""
    return _status_page(request, ui, "_status_summary.html")
