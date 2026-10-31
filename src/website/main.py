"""Application factory: ``uvicorn website.main:app``."""

import asyncio
import logging
import mimetypes
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    asynccontextmanager,
    contextmanager,
    nullcontext,
    suppress,
)
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from website.config import Settings
from website.db import connect, run_migrations
from website.services.results_sync import ResultsSyncService
from website.web.handlers import register_exception_handlers
from website.web.middleware import SecurityHeadersMiddleware
from website.web.rate_limit import limiter
from website.web.rendering import Renderer
from website.web.routes import ROUTERS
from website.web.stored_files import StoredFiles

_logger = logging.getLogger(__name__)
_RACETEC_LOG_PATH = Path("data/logs/racetec-scrape.log")


@contextmanager
def _racetec_logging(log_path: Path | None = None) -> Iterator[None]:
    """Write RaceTec integration logs to stdout and a rotating file."""
    if log_path is None:
        log_path = _RACETEC_LOG_PATH
    logger = logging.getLogger("website.integrations.racetec")
    previous_level = logger.level
    previous_propagate = logger.propagate
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers: tuple[logging.Handler, ...] = (
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        ),
    )
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        yield
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


# Serve .js/.css with correct MIME types regardless of the OS registry: on
# Windows, mimetypes can return text/plain for .js and browsers refuse it.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


async def _poll_due_syncs(app: FastAPI) -> None:
    """Run one iteration of due result synchronisations."""
    try:
        cursor = app.state.db.cursor()
        try:
            sync_service = ResultsSyncService(cursor)
            await sync_service.check_and_run_due_syncs()
        finally:
            cursor.close()
    except Exception:
        _logger.exception("Unexpected error in background results sync poller")


async def _auto_sync_loop(app: FastAPI, interval_seconds: int = 60) -> None:
    """Background task to poll and synchronise results for active fixtures."""
    with suppress(asyncio.CancelledError):
        while True:
            await asyncio.sleep(interval_seconds)
            await _poll_due_syncs(app)


def _lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        con = connect(settings.database_path)
        run_migrations(con, settings.migrations_dir)
        app.state.db = con

        logging_context = (
            _racetec_logging() if not settings.is_testing else nullcontext()
        )
        sync_task: asyncio.Task[None] | None = None
        try:
            with logging_context:
                if not settings.is_testing:
                    sync_task = asyncio.create_task(_auto_sync_loop(app))
                try:
                    yield
                finally:
                    if sync_task is not None:
                        sync_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await sync_task
        finally:
            con.close()

    return lifespan


def _mount_static_files(app: FastAPI, settings: Settings) -> None:
    # StaticFiles requires its directory to exist when mounted, which is
    # before the lifespan handler runs.
    for directory in settings.data_directories():
        directory.mkdir(parents=True, exist_ok=True)
    # Documents under /uploads and /fixture-docs may be stored gzipped.
    app.mount(
        "/uploads", StoredFiles(directory=str(settings.uploads_dir)), name="uploads"
    )
    app.mount(
        "/fixture-maps",
        StaticFiles(directory=str(settings.fixture_maps_dir)),
        name="fixture-maps",
    )
    app.mount(
        "/fixture-docs",
        StoredFiles(directory=str(settings.fixture_docs_dir)),
        name="fixture-docs",
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
