"""Tests for the background results-sync polling lifecycle."""

import asyncio
import logging
from collections.abc import Coroutine
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI

from website import main
from website.config import Settings


@pytest.mark.asyncio
async def test_poll_due_syncs_closes_cursor() -> None:
    cursor = MagicMock()
    app = FastAPI()
    app.state.db = MagicMock()
    app.state.db.cursor.return_value = cursor
    sync_service = MagicMock()
    sync_service.check_and_run_due_syncs = AsyncMock()

    with patch("website.main.ResultsSyncService", return_value=sync_service):
        await main._poll_due_syncs(app)

    sync_service.check_and_run_due_syncs.assert_awaited_once()
    cursor.close.assert_called_once()


@pytest.mark.asyncio
async def test_poll_due_syncs_closes_cursor_when_sync_fails() -> None:
    cursor = MagicMock()
    app = FastAPI()
    app.state.db = MagicMock()
    app.state.db.cursor.return_value = cursor
    sync_service = MagicMock()
    sync_service.check_and_run_due_syncs = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with patch("website.main.ResultsSyncService", return_value=sync_service):
        await main._poll_due_syncs(app)

    cursor.close.assert_called_once()


def test_racetec_logging_writes_stdout_and_rotates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log_path = tmp_path / "logs" / "racetec-scrape.log"
    logger = logging.getLogger("website.integrations.racetec")

    with main._racetec_logging(log_path):
        logger.warning("sample scraper warning")
        file_handler = next(
            handler
            for handler in logger.handlers
            if isinstance(handler, RotatingFileHandler)
        )
        assert file_handler.maxBytes == 1_000_000
        assert file_handler.backupCount == 3

    assert "sample scraper warning" in capsys.readouterr().out
    assert "sample scraper warning" in log_path.read_text(encoding="utf-8")
    assert not logger.handlers


@pytest.mark.asyncio
async def test_auto_sync_loop_polls_until_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = MagicMock()
    sleep = AsyncMock(side_effect=[None, asyncio.CancelledError])
    poll = AsyncMock()
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(main, "_poll_due_syncs", poll)

    await main._auto_sync_loop(app, interval_seconds=17)

    assert sleep.await_args_list == [call(17), call(17)]
    poll.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_auto_sync_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_path=":memory:",
        migrations_dir=Path("migrations"),
        is_testing=False,
    )
    connection = MagicMock()
    app = FastAPI()
    tasks: list[asyncio.Task[None]] = []
    create_task = asyncio.create_task

    async def wait_for_cancellation(_app: object) -> None:
        await asyncio.Event().wait()

    def track_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = create_task(coro)
        tasks.append(task)
        return task

    monkeypatch.setattr(main, "_auto_sync_loop", wait_for_cancellation)
    monkeypatch.setattr(main.asyncio, "create_task", track_task)
    log_path = tmp_path / "logs" / "racetec-scrape.log"
    monkeypatch.setattr(main, "_RACETEC_LOG_PATH", log_path)

    with (
        patch("website.main.connect", return_value=connection),
        patch("website.main.run_migrations") as run_migrations,
    ):
        async with main._lifespan(settings)(app):
            assert app.state.db is connection

    run_migrations.assert_called_once_with(connection, settings.migrations_dir)
    connection.close.assert_called_once()
    assert len(tasks) == 1
    assert tasks[0].cancelled()
    assert log_path.exists()
