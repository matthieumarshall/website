"""Health sampling and classification tests."""

from datetime import UTC, datetime
from threading import Event
from unittest.mock import Mock

import pytest

from website.config import Settings
from website.integrations.system_health import SystemHealth
from website.models.health import DiskMeasurement, Measurements
from website.services.health import (
    CAPACITY_THRESHOLDS,
    CPU_THRESHOLDS,
    LOAD_THRESHOLDS,
    HealthSampler,
    band,
    public_health,
)


@pytest.mark.parametrize(
    "thresholds", [CPU_THRESHOLDS, LOAD_THRESHOLDS, CAPACITY_THRESHOLDS]
)
def test_band_boundaries(thresholds):
    assert band(None, thresholds) == "unknown"
    assert band(thresholds[0] - 0.01, thresholds) == "low"
    assert band(thresholds[0], thresholds) == "medium"
    assert band(thresholds[1], thresholds) == "high"
    assert band(thresholds[2], thresholds) == "very high"


def test_classification_unknown_and_stale():
    snap = Measurements(
        checked_at=datetime.now(UTC),
        checked_monotonic=10,
        database="available",
        cpu=30,
        load_per_cpu=0.2,
        memory=20,
        disks=(DiskMeasurement(percent=20, used=20, free=80),),
    )
    assert public_health(snap, 55).status == "ok"
    assert public_health(snap, 55.1).status == "unavailable"
    assert public_health(snap.model_copy(update={"cpu": None}), 11).status == "degraded"
    assert (
        public_health(snap.model_copy(update={"disk_unknown": True}), 11).storage
        == "unknown"
    )
    assert (
        public_health(snap.model_copy(update={"load_per_cpu": 1.2}), 11).server_load
        == "very high"
    )


def test_sampler_reads_metrics_independently_and_handles_memory_database(
    test_db, tmp_path
):
    system = Mock()
    system.memory.return_value = 30
    system.cpu.return_value = 42
    system.load_per_cpu.return_value = 0.2
    system.disk.return_value = DiskMeasurement(percent=25, used=25, free=75)
    settings = Settings(
        database_path=":memory:",
        uploads_dir=tmp_path,
        fixture_maps_dir=tmp_path,
        admin_docs_dir=tmp_path,
        fixture_docs_dir=tmp_path,
    )
    sampler = HealthSampler(test_db, settings, system)
    first = sampler._sample(True)
    assert first.database == "available" and first.in_memory
    assert first.cpu is None and first.load_per_cpu is None
    assert first.database_size is None
    system.memory.side_effect = OSError("unavailable")
    second = sampler._sample(False)
    assert second.cpu == 42 and second.memory is None
    assert public_health(second, second.checked_monotonic).status == "degraded"
    test_db.execute("DROP TABLE _migrations")
    assert sampler._sample(False).database == "unavailable"


def test_sampler_lifecycle_uses_one_worker(test_db, tmp_path):
    sampled = Event()
    system = Mock()
    system.memory.side_effect = lambda: sampled.set() or 20.0
    system.load_per_cpu.return_value = 0.1
    system.disk.return_value = DiskMeasurement(percent=20, used=20, free=80)
    settings = Settings(
        database_path=":memory:",
        uploads_dir=tmp_path,
        fixture_maps_dir=tmp_path,
        admin_docs_dir=tmp_path,
        fixture_docs_dir=tmp_path,
    )
    sampler = HealthSampler(test_db, settings, system)
    sampler.start()
    assert sampled.wait(5)
    sampler.stop()
    assert sampler.snapshot() is not None
    system.prime_cpu.assert_called_once()


def test_file_database_sizes_and_disk_failure_are_independent(test_db, tmp_path):
    db_path = tmp_path / "site.duckdb"
    db_path.write_bytes(b"database")
    wal_path = tmp_path / "site.duckdb.wal"
    wal_path.write_bytes(b"wal")
    system = Mock()
    system.memory.return_value = 20
    system.cpu.return_value = 25
    system.load_per_cpu.return_value = 0.2
    system.disk.side_effect = OSError("disk unavailable")
    system.file_size.side_effect = lambda path: path.stat().st_size
    settings = Settings(
        database_path=str(db_path),
        uploads_dir=tmp_path,
        fixture_maps_dir=tmp_path,
        admin_docs_dir=tmp_path,
        fixture_docs_dir=tmp_path,
    )
    result = HealthSampler(test_db, settings, system)._sample(False)
    assert result.database == "available"
    assert result.disk_unknown
    assert result.database_size == 8 and result.wal_size == 3
    assert public_health(result, result.checked_monotonic).storage == "unknown"


def test_system_adapter_uses_host_metrics(monkeypatch, tmp_path):
    import psutil

    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 42.0)
    monkeypatch.setattr(psutil, "cpu_count", lambda: 4)
    monkeypatch.setattr(psutil, "getloadavg", lambda: (2.0, 1.0, 0.5))
    monkeypatch.setattr(psutil, "virtual_memory", lambda: Mock(percent=50.0))
    monkeypatch.setattr(
        psutil, "disk_usage", lambda path: Mock(percent=60, used=60, free=40)
    )
    adapter = SystemHealth()
    adapter.prime_cpu()
    assert adapter.cpu() == 42
    assert adapter.load_per_cpu() == 0.5
    assert adapter.memory() == 50
    assert adapter.disk(tmp_path).free == 40
    file = tmp_path / "sample"
    file.write_bytes(b"123")
    assert adapter.file_size(file) == 3
    monkeypatch.setattr(psutil, "cpu_count", lambda: None)
    with pytest.raises(ValueError):
        adapter.load_per_cpu()
