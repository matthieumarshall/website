"""
CLI script to create a new fixture (round) within a season.

Usage:
    python -m website.seed_fixture <season_name> <title> <date> <location_name> [options]

Positional arguments:
    season_name    Name of the existing season, e.g. "2025-2026"
    title          Fixture title, e.g. "Round 1"
    date           Date in YYYY-MM-DD format, e.g. "2025-11-02"
    location_name  Venue name, e.g. "Cirencester Park"

Optional arguments:
    --address      Postal address of the venue (default: empty)
    --travel       Travel instructions (default: empty)

Example:
    python -m website.seed_fixture "2025-2026" "Round 1" "2025-11-02" "Cirencester Park"
    python -m website.seed_fixture "2025-2026" "Round 2" "2025-12-07" "Hampden Park" \\
        --address "Hampden Park, Eastbourne, BN22 9QH" \\
        --travel "Parking available on site."

Exits with an error if the season does not exist or a fixture with the same
title already exists in that season.
"""

import argparse
import sys

import duckdb

from website import repository
from website.database import _get_db_path, run_migrations


def create_fixture(
    season_name: str,
    title: str,
    date: str,
    location_name: str,
    address: str,
    travel_instructions: str,
) -> None:
    db_path = _get_db_path()
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)

        seasons = repository.list_seasons(con)
        matching = [s for s in seasons if s.name.lower() == season_name.lower()]
        if not matching:
            available = ", ".join(f'"{s.name}"' for s in seasons) or "none"
            print(
                f"Error: No season found with name '{season_name}'. "
                f"Available seasons: {available}"
            )
            sys.exit(1)
        season = matching[0]

        fixtures = repository.list_fixtures_for_season(con, season.id)
        if any(f.title.lower() == title.lower() for f in fixtures):
            print(f"Error: Fixture '{title}' already exists in season '{season.name}'.")
            sys.exit(1)

        fixture = repository.create_fixture(
            con,
            season_id=season.id,
            title=title,
            date=date,
            location_name=location_name,
            address=address,
            timetable=[],
            travel_instructions=travel_instructions,
        )
        print(
            f"Created fixture '{fixture.title}' (id={fixture.id}) "
            f"on {fixture.date} in season '{season.name}'."
        )
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a new fixture within a season."
    )
    parser.add_argument("season_name", help='Season name, e.g. "2025-2026"')
    parser.add_argument("title", help='Fixture title, e.g. "Round 1"')
    parser.add_argument("date", help='Date in YYYY-MM-DD format, e.g. "2025-11-02"')
    parser.add_argument("location_name", help='Venue name, e.g. "Cirencester Park"')
    parser.add_argument("--address", default="", help="Postal address of the venue")
    parser.add_argument(
        "--travel", default="", dest="travel_instructions", help="Travel instructions"
    )
    args = parser.parse_args()
    create_fixture(
        args.season_name,
        args.title,
        args.date,
        args.location_name,
        args.address,
        args.travel_instructions,
    )
