"""
CLI script to import race results for a fixture from a CSV file.

Usage:
    python -m cli.seed_results <season_name> <fixture_title> <race_name> <csv_file>

The CSV file must have a header row with these columns (order does not matter):
    position, athlete_name, time, category, gender
    [optional: race_number, category_position, gender_position, club]

Example:
    python -m cli.seed_results "2025-2026" "Round 1" "Men" results/men.csv
    python -m cli.seed_results "2025-2026" "Round 1" "U13 Girls" results/u13_girls.csv

Run the command once per race. If a race with the same name already exists on
that fixture the script will exit without inserting duplicates — delete the race
first if you need to re-import.
"""

import argparse
import csv
import io
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

# Map raw CSV category display names to pyresults category codes.
# These unambiguous mappings do not depend on gender.
_CATEGORY_NAME_MAP: dict[str, str] = {
    "senior men": "SM",
    "senior women": "SW",
    "u20 men": "U20M",
    "u20 women": "U20W",
    "u9 boys": "U9B",
    "u9 girls": "U9G",
    "u11 boys": "U11B",
    "u11 girls": "U11G",
    "u13 boys": "U13B",
    "u13 girls": "U13G",
    "u15 boys": "U15B",
    "u15 girls": "U15G",
    "u17 men": "U17M",
    "u17 women": "U17W",
}

# Gender-dependent mappings: (gender_lowercase, category_lower) → code.
# Used for veteran codes that omit the gender prefix in the timing output.
_GENDER_CATEGORY_MAP: dict[tuple[str, str], str] = {
    ("male", "v40"): "MV40",
    ("female", "v40"): "WV40",
    ("male", "v50"): "MV50",
    ("female", "v50"): "WV50",
    ("male", "v60"): "MV60",
    ("female", "v60"): "WV60",
    ("male", "v70"): "MV70",
    ("female", "v70"): "WV70",
}


def _normalise_category(raw_category: str, gender: str) -> str:
    """Normalise a raw CSV category string to a pyresults category code.

    Priority:
    1. If the raw value already matches a valid code (case-insensitive), return it.
    2. Check the gender-dependent veteran lookup table.
    3. Check the unambiguous display-name table.
    4. Return the raw value unchanged and print a warning.
    """
    from pyresults import get_valid_category_codes

    valid = get_valid_category_codes()
    stripped = raw_category.strip()
    upper = stripped.upper()

    # Case-insensitive exact match against known codes
    for code in valid:
        if code.upper() == upper:
            return code

    cat_lower = stripped.lower()

    # Gender-dependent mapping (e.g. "V40" + "male" → "MV40")
    gender_lower = gender.strip().lower()
    gender_mapped = _GENDER_CATEGORY_MAP.get((gender_lower, cat_lower))
    if gender_mapped:
        return gender_mapped

    # Unambiguous display-name mapping
    name_mapped = _CATEGORY_NAME_MAP.get(cat_lower)
    if name_mapped:
        return name_mapped

    print(
        f"Warning: unrecognised category '{stripped}' (gender={gender}); "
        "storing as-is. Check pyresults category codes.",
        file=sys.stderr,
    )
    return stripped


def _int_or_none(value: str) -> int | None:
    stripped = value.strip()
    if stripped == "":
        return None
    return int(stripped)


def _import_results(
    con: duckdb.DuckDBPyConnection,
    season_name: str,
    fixture_title: str,
    race_name: str,
    csv_path: Path,
) -> tuple[int, int]:
    """Import race results from a CSV file.

    Returns a (inserted_count, fixture_id) tuple on success.
    Raises ValueError for any validation or parse error.
    """
    if not csv_path.exists():
        raise ValueError(f"CSV file not found: {csv_path}")

    seasons = repository.list_seasons(con)
    matching_seasons = [s for s in seasons if s.name.lower() == season_name.lower()]
    if not matching_seasons:
        available = ", ".join(f'"{s.name}"' for s in seasons) or "none"
        raise ValueError(
            f"No season found with name '{season_name}'. Available seasons: {available}"
        )
    season = matching_seasons[0]

    fixtures = repository.list_fixtures_for_season(con, season.id)
    matching_fixtures = [
        f for f in fixtures if f.title.lower() == fixture_title.lower()
    ]
    if not matching_fixtures:
        available = ", ".join(f'"{f.title}"' for f in fixtures) or "none"
        raise ValueError(
            f"No fixture found with title '{fixture_title}' in season "
            f"'{season.name}'. Available fixtures: {available}"
        )
    fixture = matching_fixtures[0]

    existing_races = repository.list_races_for_fixture(con, fixture.id)
    if any(r.name.lower() == race_name.lower() for r in existing_races):
        raise ValueError(
            f"Race '{race_name}' already exists for fixture "
            f"'{fixture.title}'. Delete it first if you want to re-import."
        )

    # Decode the CSV in Python first (handles UTF-16 BOM and CRLF line endings
    # that confuse DuckDB's sniffer), then parse with csv.DictReader.
    raw = csv_path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        text = raw[2:].decode("utf-16-le", errors="replace")
    elif raw[:2] == b"\xfe\xff":
        text = raw[2:].decode("utf-16-be", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    # Normalise headers: strip whitespace, lowercase, map display names
    raw_fields = [f.strip() for f in (reader.fieldnames or [])]
    normalised = {_HEADER_MAP.get(f.lower(), f.lower()) for f in raw_fields}
    field_remap = {
        f.strip(): _HEADER_MAP.get(f.strip().lower(), f.strip().lower())
        for f in raw_fields
    }

    missing = _REQUIRED_HEADERS - normalised
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {', '.join(sorted(missing))}"
        )

    raw_rows = list(reader)
    rows = []
    for row in raw_rows:
        mapped = {field_remap[k.strip()]: v for k, v in row.items() if k is not None}
        pos = mapped.get("position", "").strip()
        if pos and pos.lstrip("-").isdigit():
            rows.append(mapped)

    if not rows:
        raise ValueError("CSV file contains no data rows.")

    con.execute("BEGIN")
    try:
        race = repository.create_race(con, fixture_id=fixture.id, name=race_name)
        inserted = 0
        for i, row in enumerate(rows, start=2):  # line 2 = first data row
            try:
                repository.create_result(
                    con,
                    race_id=race.id,
                    position=int(row["position"].strip()),
                    athlete_name=row["athlete_name"].strip(),
                    time=row["time"].strip(),
                    category=_normalise_category(
                        row["category"].strip(), row.get("gender", "")
                    ),
                    gender=row["gender"].strip(),
                    race_number=_int_or_none(row.get("race_number", "")),
                    category_position=_int_or_none(row.get("category_position", "")),
                    gender_position=_int_or_none(row.get("gender_position", "")),
                    club=row.get("club", "").strip() or None,
                )
                inserted += 1
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Error on CSV row {i}: {exc}") from exc
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return inserted, fixture.id


def import_results(
    season_name: str, fixture_title: str, race_name: str, csv_path: Path
) -> None:
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        try:
            inserted, fixture_id = _import_results(
                con, season_name, fixture_title, race_name, csv_path
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        print(
            f"Imported {inserted} result(s) into race '{race_name}' "
            f"for fixture '{fixture_title}' (id={fixture_id})."
        )
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import race results for a fixture from a CSV file."
    )
    parser.add_argument("season_name", help='Season name, e.g. "2025-2026"')
    parser.add_argument("fixture_title", help='Fixture title, e.g. "Round 1"')
    parser.add_argument("race_name", help='Name of the race, e.g. "Men" or "U13 Girls"')
    parser.add_argument("csv_file", type=Path, help="Path to the CSV file")
    args = parser.parse_args()
    import_results(args.season_name, args.fixture_title, args.race_name, args.csv_file)
