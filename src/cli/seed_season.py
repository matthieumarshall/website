"""
CLI script to create a new season.

Usage:
    python -m cli.seed_season <season_name>

Example:
    python -m cli.seed_season "2025-2026"

Exits with an error if a season with that name already exists.
"""

import argparse
import sys

import duckdb

from website import repository
from website.database import _get_db_path, run_migrations
from website.models import Season


def _create_season(con: duckdb.DuckDBPyConnection, season_name: str) -> Season:
    """Create a season in the database.

    Raises ValueError if a season with the same name (case-insensitive) already exists.
    """
    existing = repository.list_seasons(con)
    if any(s.name.lower() == season_name.lower() for s in existing):
        raise ValueError(f"Season '{season_name}' already exists.")
    return repository.create_season(con, name=season_name)


def create_season(season_name: str) -> None:
    db_path = _get_db_path()
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        try:
            season = _create_season(con, season_name)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        print(f"Created season '{season.name}' (id={season.id}).")
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new season.")
    parser.add_argument("season_name", help='Season name, e.g. "2025-2026"')
    args = parser.parse_args()
    create_season(args.season_name)
