"""Application factory: ``uvicorn website.main:app``."""

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from website.config import Settings
from website.db import connect, run_migrations
from website.web.handlers import register_exception_handlers
from website.web.middleware import SecurityHeadersMiddleware
from website.web.rate_limit import limiter
from website.web.rendering import Renderer
from website.web.routes import ROUTERS

# Serve .js/.css with correct MIME types regardless of the OS registry: on
# Windows, mimetypes can return text/plain for .js and browsers refuse it.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def _lifespan(settings: Settings):  # noqa: ANN202 — returns a lifespan context factory
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        con = connect(settings.database_path)
        run_migrations(con, settings.migrations_dir)
        app.state.db = con
        yield
        con.close()

    return lifespan


def _mount_static_files(app: FastAPI, settings: Settings) -> None:
    # StaticFiles requires its directory to exist when mounted, which is
    # before the lifespan handler runs.
    for directory in settings.data_directories():
        directory.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads"
    )
    app.mount(
        "/fixture-maps",
        StaticFiles(directory=str(settings.fixture_maps_dir)),
        name="fixture-maps",
    )
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the website application."""
    settings = settings or Settings.from_env()
    app = FastAPI(lifespan=_lifespan(settings))
    app.state.settings = settings
    app.state.renderer = Renderer(
        settings.templates_dir, settings.stripe_publishable_key
    )
    limiter.enabled = not settings.is_testing
    app.state.limiter = limiter

    register_exception_handlers(app)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.is_production,
        same_site="lax",
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    _mount_static_files(app, settings)
    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
