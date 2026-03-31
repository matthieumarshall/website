"""
CLI script to import race results for a fixture from a CSV file.

Usage:
    python -m website.seed_results <fixture_id> <race_name> <csv_file>

The CSV file must have a header row with these columns (order does not matter):
    position, athlete_name, time, category, gender
    [optional: race_number, category_position, gender_position, club]

Example:
    python -m website.seed_results 3 "Men" results/men.csv
    python -m website.seed_results 3 "U13 Girls" results/u13_girls.csv

Run the command once per race. If a race with the same name already exists on
that fixture the script will exit without inserting duplicates — delete the race
first if you need to re-import.
"""

import argparse
import csv
import sys
from pathlib import Path

import duckdb

from website import repository
from website.database import _get_db_path, run_migrations

_REQUIRED_HEADERS = {"position", "athlete_name", "time", "category", "gender"}
_OPTIONAL_HEADERS = {"race_number", "category_position", "gender_position", "club"}

# Map display column names (as exported from Excel/Tempo) to internal names
_HEADER_MAP = {
    "pos": "position",
    "race no": "race_number",
    "name": "athlete_name",
    "time": "time",
    "category": "category",
    "cat pos": "category_position",
    "gender": "gender",
    "gen pos": "gender_position",
    "club": "club",
}


def _int_or_none(value: str) -> int | None:
    stripped = value.strip()
    if stripped == "":
        return None
    return int(stripped)


def import_results(fixture_id: int, race_name: str, csv_path: Path) -> None:
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    db_path = _get_db_path()
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)

        fixture = repository.get_fixture_by_id(con, fixture_id)
        if fixture is None:
            print(f"Error: No fixture found with id={fixture_id}.")
            sys.exit(1)

        # Prevent duplicate races
        existing = repository.list_races_for_fixture(con, fixture_id)
        if any(r.name.lower() == race_name.lower() for r in existing):
            print(
                f"Error: Race '{race_name}' already exists for fixture "
                f"'{fixture.title}'. Delete it first if you want to re-import."
            )
            sys.exit(1)

        # Detect encoding — files exported from Excel are often UTF-16 LE with BOM
        raw = csv_path.read_bytes()
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"

        with csv_path.open(newline="", encoding=encoding) as fh:
            reader = csv.DictReader(fh)
            # Normalise headers: strip whitespace, lowercase, map display names
            raw_fields = [f.strip() for f in (reader.fieldnames or [])]
            normalised = {_HEADER_MAP.get(f.lower(), f.lower()) for f in raw_fields}
            field_remap = {
                f.strip(): _HEADER_MAP.get(f.strip().lower(), f.strip().lower())
                for f in raw_fields
            }

            missing = _REQUIRED_HEADERS - normalised
            if missing:
                print(
                    f"Error: CSV is missing required columns: {', '.join(sorted(missing))}"
                )
                sys.exit(1)

            rows = [
                {field_remap[k.strip()]: v for k, v in row.items() if k is not None}
                for row in reader
            ]

        if not rows:
            print("Error: CSV file contains no data rows.")
            sys.exit(1)

        race = repository.create_race(con, fixture_id=fixture_id, name=race_name)

        inserted = 0
        for i, row in enumerate(rows, start=2):  # line 2 = first data row
            try:
                repository.create_result(
                    con,
                    race_id=race.id,
                    position=int(row["position"].strip()),
                    athlete_name=row["athlete_name"].strip(),
                    time=row["time"].strip(),
                    category=row["category"].strip(),
                    gender=row["gender"].strip(),
                    race_number=_int_or_none(row.get("race_number", "")),
                    category_position=_int_or_none(row.get("category_position", "")),
                    gender_position=_int_or_none(row.get("gender_position", "")),
                    club=row.get("club", "").strip() or None,
                )
                inserted += 1
            except (ValueError, KeyError) as exc:
                print(f"Error on CSV row {i}: {exc}")
                con.close()
                sys.exit(1)

        print(
            f"Imported {inserted} result(s) into race '{race_name}' "
            f"for fixture '{fixture.title}' (id={fixture_id})."
        )
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import race results for a fixture from a CSV file."
    )
    parser.add_argument("fixture_id", type=int, help="ID of the fixture")
    parser.add_argument("race_name", help='Name of the race, e.g. "Men" or "U13 Girls"')
    parser.add_argument("csv_file", type=Path, help="Path to the CSV file")
    args = parser.parse_args()
    import_results(args.fixture_id, args.race_name, args.csv_file)
