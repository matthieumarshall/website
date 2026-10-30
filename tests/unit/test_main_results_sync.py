"""Tests for the background results-sync polling lifecycle."""

import asyncio
from collections.abc import Coroutine
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
