"""Immutable status measurements and public health responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Band = Literal["low", "medium", "high", "very high", "unknown"]
Availability = Literal["available", "unavailable", "unknown"]


class DiskMeasurement(BaseModel):
    """Usage of a filesystem, with no path in the presentation model."""

    model_config = ConfigDict(frozen=True)
    percent: float
    used: int
    free: int


class Measurements(BaseModel):
    """Private readings collected together by the background sampler."""

    model_config = ConfigDict(frozen=True)
    checked_at: datetime
    checked_monotonic: float
    database: Availability = "unknown"
    cpu: float | None = None
    load_per_cpu: float | None = None
    memory: float | None = None
    disks: tuple[DiskMeasurement, ...] = ()
    disk_unknown: bool = False
    database_size: int | None = None
    wal_size: int | None = None
    in_memory: bool = False


class PublicHealth(BaseModel):
    """Information that can safely be returned to any visitor."""

    model_config = ConfigDict(frozen=True)
    status: Literal["ok", "degraded", "unavailable"]
    database: Availability
    storage: Band
    memory: Band
    server_load: Band
    checked_at: datetime | None
