"""System resource readings used by the health sampler."""

from pathlib import Path

import psutil

from website.models.health import DiskMeasurement


class SystemHealth:
    """Read host metrics without invoking subprocesses."""

    def prime_cpu(self) -> None:
        """Start CPU sampling on the dedicated sampler thread."""
        psutil.cpu_percent(interval=None)

    def cpu(self) -> float:
        """Return CPU utilisation since the previous sample on this thread."""
        return psutil.cpu_percent(interval=None)

    def load_per_cpu(self) -> float:
        """Return one-minute system load divided by logical CPU count."""
        count = psutil.cpu_count()
        if not count:
            raise ValueError("CPU count unavailable")
        return psutil.getloadavg()[0] / count

    def memory(self) -> float:
        """Return host memory utilisation based on available memory."""
        return float(psutil.virtual_memory().percent)

    def disk(self, path: Path) -> DiskMeasurement:
        """Return usage for the filesystem containing an existing path."""
        usage = psutil.disk_usage(str(path))
        return DiskMeasurement(percent=usage.percent, used=usage.used, free=usage.free)

    def file_size(self, path: Path) -> int:
        """Return a file size in bytes."""
        return path.stat().st_size
