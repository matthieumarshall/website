"""Structured JSON logging for import operations with console summaries.

Provides centralized import logging with support for info/warning/error levels,
JSON-lines formatted logs, and human-readable summary reports.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ImportLogger:
    """Structured logger for import operations with JSON output and summaries.

    Logs are written to JSON-lines format for machine parsing and to stdout
    for human consumption. Summary reports are printed after import completion.

    Attributes:
        log_file: Path to JSON-lines log file (or None for no file logging)
        records: List of all log records (for summary generation)
        stats: Statistics tracking (counts by level and stage)
    """

    def __init__(self, log_file: Optional[Path] = None) -> None:
        """Initialize the import logger.

        Args:
            log_file: Path to write JSON-lines logs. If None, only stdout logging.
        """
        self.log_file = log_file
        self.records: list[dict] = []
        self.stats: dict[str, Any] = {
            "info": 0,
            "warning": 0,
            "error": 0,
            "stages": {},
        }
        self.start_time = datetime.now()

        # Ensure log directory exists
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write_log(self, level: str, message: dict) -> None:
        """Write a log record to file and memory.

        Args:
            level: Log level ('info', 'warning', 'error')
            message: Dictionary with log fields
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            **message,
        }

        # Track stats
        self.stats[level] += 1
        stage = message.get("stage", "unknown")
        if stage not in self.stats["stages"]:
            self.stats["stages"][stage] = {"info": 0, "warning": 0, "error": 0}
        self.stats["stages"][stage][level] += 1

        # Store record
        self.records.append(record)

        # Write to file
        if self.log_file:
            with open(self.log_file, "a") as f:
                json.dump(record, f)
                f.write("\n")

    def info(self, stage: str, **fields) -> None:
        """Log an info-level message.

        Args:
            stage: Import stage name (e.g., 'season_create', 'result_insert')
            **fields: Additional fields to log
        """
        self._write_log("info", {"stage": stage, **fields})

    def warning(self, stage: str, **fields) -> None:
        """Log a warning-level message.

        Args:
            stage: Import stage name
            **fields: Additional fields to log (e.g., file, row, issue, detail)
        """
        self._write_log("warning", {"stage": stage, **fields})

    def error(self, stage: str, **fields) -> None:
        """Log an error-level message.

        Args:
            stage: Import stage name
            **fields: Additional fields to log (e.g., file, reason)
        """
        self._write_log("error", {"stage": stage, **fields})

    def summary(self) -> str:
        """Generate and return a human-readable summary report.

        Returns:
            Formatted summary string with import statistics and duration.
        """
        duration = datetime.now() - self.start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)

        # Count records by category (inferred from log records)
        results_count = sum(
            1
            for r in self.records
            if r.get("stage") == "result_insert" and r["level"] == "info"
        )
        standings_count = sum(
            1
            for r in self.records
            if r.get("stage") == "standing_insert" and r["level"] == "info"
        )
        seasons_count = sum(
            1
            for r in self.records
            if r.get("stage") == "season_create" and r["level"] == "info"
        )
        fixtures_count = sum(
            1
            for r in self.records
            if r.get("stage") == "fixture_create" and r["level"] == "info"
        )
        races_count = sum(
            1
            for r in self.records
            if r.get("stage") == "race_create" and r["level"] == "info"
        )

        report = [
            "",
            "═" * 60,
            f"Import Summary — {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "═" * 60,
        ]

        if results_count > 0 or standings_count > 0:
            report.append("")
            if results_count > 0:
                report.append(
                    f"Results:      {results_count:6d} imported | "
                    f"{self.stats['stages'].get('result_insert', {}).get('warning', 0):3d} warnings"
                )
            if standings_count > 0:
                report.append(
                    f"Standings:    {standings_count:6d} imported | "
                    f"{self.stats['stages'].get('standing_insert', {}).get('warning', 0):3d} warnings"
                )

        report.append("─" * 60)

        if seasons_count > 0 or fixtures_count > 0:
            report.append(f"Seasons created:  {seasons_count}")
            report.append(f"Fixtures created: {fixtures_count}")
            report.append(f"Races created:    {races_count}")
            report.append("─" * 60)

        report.append(
            f"Errors:    {self.stats['error']:<3d} | "
            f"Warnings:  {self.stats['warning']:<3d}"
        )
        report.append(f"Duration:  {minutes}m {seconds}s")

        if self.log_file:
            report.append(f"Log file:  {self.log_file}")

        report.extend(["═" * 60, ""])

        return "\n".join(report)

    def print_summary(self) -> None:
        """Print the summary report to stdout."""
        print(self.summary())

    def write_summary(self, path: Optional[Path] = None) -> None:
        """Write summary report to a file.

        Args:
            path: Path to write summary (defaults to {log_file}.summary)
        """
        if path is None:
            if self.log_file is None:
                return
            path = Path(str(self.log_file) + ".summary")

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.summary())
