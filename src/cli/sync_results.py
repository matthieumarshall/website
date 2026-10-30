"""CLI tool to poll and synchronise race results from Tempo Events / RaceTec."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import duckdb

from website.db import get_db_path, run_migrations
from website.services.results_sync import ResultsSyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_logger = logging.getLogger("cli.sync_results")


async def _run(fixture_id: int | None = None, url: str | None = None) -> int:
    db_path = get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        service = ResultsSyncService(con)

        if fixture_id is not None:
            _logger.info("Running sync for fixture ID %s...", fixture_id)
            summary = await service.sync_fixture_from_url(fixture_id, url=url)
            if summary.success:
                _logger.info(
                    "Sync succeeded: %s finishers across %s races (%s)",
                    summary.finishers_synced,
                    summary.races_synced,
                    ", ".join(summary.races),
                )
                return 0
            else:
                _logger.error("Sync failed: %s", summary.error)
                return 1
        else:
            _logger.info("Checking and running due auto-syncs across all fixtures...")
            summaries = await service.check_and_run_due_syncs()
            _logger.info("Completed %s auto-sync runs.", len(summaries))
            for s in summaries:
                status = "SUCCESS" if s.success else f"FAILED ({s.error})"
                _logger.info(
                    "Fixture %s: %s (%s finishers)",
                    s.fixture_id,
                    status,
                    s.finishers_synced,
                )
            return 0
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronise race results from Tempo Events / RaceTec into DuckDB."
    )
    parser.add_argument(
        "--fixture-id",
        type=int,
        default=None,
        help="Specific fixture ID to synchronise on demand.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Optional results URL override (if fixture does not have one set).",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(_run(fixture_id=args.fixture_id, url=args.url))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
