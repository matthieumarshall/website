"""Background health sampling and public status classification."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Literal, TypeVar

from website.config import Settings
from website.db import Connection
from website.integrations.system_health import SystemHealth
from website.models.health import Band, DiskMeasurement, Measurements, PublicHealth
from website.repository.health import probe

_LOG = logging.getLogger(__name__)
SAMPLE_SECONDS = 15
STALE_SECONDS = 45
CPU_THRESHOLDS = (50.0, 75.0, 90.0)
LOAD_THRESHOLDS = (0.5, 0.75, 1.0)
CAPACITY_THRESHOLDS = (70.0, 85.0, 95.0)
_LEVELS: tuple[Band, ...] = ("low", "medium", "high", "very high")
T = TypeVar("T")


def band(value: float | None, thresholds: tuple[float, float, float]) -> Band:
    """Classify a measured value; absent values remain unknown."""
    if value is None:
        return "unknown"
    return _LEVELS[sum(value >= threshold for threshold in thresholds)]


def _worse(first: Band, second: Band) -> Band:
    if "unknown" in (first, second):
        return "unknown"
    return max((first, second), key=_LEVELS.index)


def public_health(snapshot: Measurements | None, now: float) -> PublicHealth:
    """Classify an immutable snapshot without revealing private readings."""
    if snapshot is None:
        return PublicHealth(
            status="unavailable",
            database="unknown",
            storage="unknown",
            memory="unknown",
            server_load="unknown",
            checked_at=None,
        )
    storage = (
        "unknown"
        if snapshot.disk_unknown or not snapshot.disks
        else band(max(disk.percent for disk in snapshot.disks), CAPACITY_THRESHOLDS)
    )
    memory = band(snapshot.memory, CAPACITY_THRESHOLDS)
    load = _worse(
        band(snapshot.cpu, CPU_THRESHOLDS), band(snapshot.load_per_cpu, LOAD_THRESHOLDS)
    )
    status: Literal["ok", "degraded", "unavailable"]
    if (
        now - snapshot.checked_monotonic > STALE_SECONDS
        or snapshot.database != "available"
    ):
        status = "unavailable"
    elif any(
        level in ("high", "very high", "unknown") for level in (storage, memory, load)
    ):
        status = "degraded"
    else:
        status = "ok"
    return PublicHealth(
        status=status,
        database=snapshot.database,
        storage=storage,
        memory=memory,
        server_load=load,
        checked_at=snapshot.checked_at,
    )


def _read(operation: Callable[[], T]) -> T | None:
    try:
        return operation()
    except Exception:  # noqa: BLE001 - optional metrics must not stop sampling.
        _LOG.warning("Health measurement failed", exc_info=True)
        return None


class HealthSampler:
    """Own a single sampler thread and publish immutable snapshots."""

    def __init__(
        self, db: Connection, settings: Settings, system: SystemHealth | None = None
    ) -> None:
        """Bind the sampler to the application connection and configuration."""
        self._db = db
        self._settings = settings
        self._system = system or SystemHealth()
        self._stop = Event()
        self._lock = Lock()
        self._snapshot: Measurements | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start the application-owned worker."""
        self._thread = Thread(target=self._run, name="health-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the worker before its database connection is closed."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def snapshot(self) -> Measurements | None:
        """Return the most recently completed sample."""
        with self._lock:
            return self._snapshot

    def _probe(self) -> bool:
        cursor = self._db.cursor()
        try:
            probe(cursor)
        finally:
            cursor.close()
        return True

    def _sample(self, initial: bool) -> Measurements:
        settings = self._settings
        memory = _read(self._system.memory)
        cpu = None if initial else _read(self._system.cpu)
        load = _read(self._system.load_per_cpu)
        if initial:
            load = None  # Windows needs time to initialise its load average.
        db_ok = _read(self._probe)
        in_memory = settings.database_path == ":memory:"
        db_path = Path(settings.database_path).resolve() if not in_memory else None
        root = Path(Path.cwd().resolve().anchor)
        paths = [root, *(p.resolve() for p in settings.data_directories())]
        if db_path is not None:
            paths.append(db_path.parent)
        readings = [
            _read(partial(self._system.disk, path)) for path in dict.fromkeys(paths)
        ]
        disks = tuple(disk for disk in readings if isinstance(disk, DiskMeasurement))
        database_size = (
            _read(lambda: self._system.file_size(db_path)) if db_path else None
        )
        wal = Path(f"{db_path}.wal") if db_path else None
        wal_size = (
            _read(lambda: self._system.file_size(wal))
            if wal and wal.exists()
            else 0
            if wal
            else None
        )
        return Measurements(
            checked_at=datetime.now(UTC),
            checked_monotonic=time.monotonic(),
            database="available" if db_ok else "unavailable",
            cpu=cpu,
            load_per_cpu=load,
            memory=memory,
            disks=disks,
            disk_unknown=any(disk is None for disk in readings),
            database_size=database_size,
            wal_size=wal_size,
            in_memory=in_memory,
        )

    def _run(self) -> None:
        _read(self._system.prime_cpu)
        initial = True
        while not self._stop.is_set():
            sample = _read(partial(self._sample, initial))
            if sample is not None:
                with self._lock:
                    self._snapshot = sample
            initial = False
            if self._stop.wait(SAMPLE_SECONDS):
                break
