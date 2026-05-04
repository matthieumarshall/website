"""Shared helpers for historic data migration scripts.

Not intended to be run directly — imported by migrate_results.py and
migrate_standings.py.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent


def open_db() -> duckdb.DuckDBPyConnection:
    """Open a direct connection to the persistent DuckDB database.

    Runs migrations automatically so the schema is always up to date.
    """
    # Import here to ensure the package is on sys.path when running via
    # `uv run python scripts/...`
    sys.path.insert(0, str(_ROOT / "src"))
    from website.database import _get_db_path, run_migrations  # noqa: PLC0415

    db_path = _get_db_path()
    con = duckdb.connect(db_path)
    run_migrations(con)
    return con


# ---------------------------------------------------------------------------
# Season / fixture lookups
# ---------------------------------------------------------------------------


def find_season_id(con: duckdb.DuckDBPyConnection, season_name: str) -> int:
    """Return the id for *season_name* (case-insensitive).

    Raises SystemExit with a helpful message if the season is not found.
    """
    row = con.execute(
        "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
    ).fetchone()
    if row is None:
        available = con.execute(
            "SELECT name FROM seasons ORDER BY name DESC"
        ).fetchall()
        names = ", ".join(f'"{r[0]}"' for r in available) or "none"
        sys.exit(f"Season '{season_name}' not found. Available seasons: {names}")
    return int(row[0])


def create_season_if_missing(con: duckdb.DuckDBPyConnection, season_name: str) -> int:
    """Return the id for *season_name*, creating the season row if absent."""
    row = con.execute(
        "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
    ).fetchone()
    if row:
        return int(row[0])
    con.execute("INSERT INTO seasons (name) VALUES (?)", [season_name])
    row = con.execute(
        "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    print(f"  Created season: {season_name!r} (id={row[0]})")
    return int(row[0])


def find_fixture_by_date(
    con: duckdb.DuckDBPyConnection, fixture_date: date, season_id: int
) -> int | None:
    """Return the fixture id for *fixture_date* in *season_id*, or None."""
    row = con.execute(
        "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
        [season_id, fixture_date],
    ).fetchone()
    return int(row[0]) if row else None


def list_fixtures_for_season_ordered(
    con: duckdb.DuckDBPyConnection, season_id: int
) -> list[tuple[int, date]]:
    """Return [(fixture_id, date), …] sorted by date ASC.

    The 1-based index of each entry corresponds to round number (R1, R2, …).
    """
    rows = con.execute(
        "SELECT id, date FROM fixtures WHERE season_id = ? ORDER BY date ASC",
        [season_id],
    ).fetchall()
    return [(int(r[0]), r[1]) for r in rows]


def fixture_has_races(con: duckdb.DuckDBPyConnection, fixture_id: int) -> bool:
    """Return True if *fixture_id* already has any races (idempotency guard)."""
    row = con.execute(
        "SELECT COUNT(*) FROM races WHERE fixture_id = ?", [fixture_id]
    ).fetchone()
    return bool(row and row[0] > 0)


def venue_name_from_filename(raw: str) -> str:
    """Convert a CamelCase or hyphenated venue filename fragment to a readable name.

    Examples::

        'BicesterHeritage'          → 'Bicester Heritage'
        'Ascott-under-Wychwood'     → 'Ascott under Wychwood'
        'GreenHillFarmBletchingdon' → 'Green Hill Farm Bletchingdon'
    """
    import re as _re  # noqa: PLC0415

    # Insert space before each uppercase letter that follows a lowercase letter.
    name = _re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    # Replace hyphens with spaces.
    name = name.replace("-", " ")
    # Collapse multiple spaces.
    return _re.sub(r" +", " ", name).strip()


def get_or_create_fixture(
    con: duckdb.DuckDBPyConnection,
    season_id: int,
    round_num: int,
    fixture_date: "date",
    venue_raw: str,
) -> int:
    """Return the fixture id for *fixture_date* in *season_id*, creating it if absent.

    The fixture title is derived as ``'Round N'`` and the location name is
    derived by splitting the CamelCase/hyphenated *venue_raw* string.

    This function inserts directly into the ``fixtures`` table to bypass the
    application-level fixture-count limit (which is designed for admin UI use,
    not bulk migration).
    """
    existing = find_fixture_by_date(con, fixture_date, season_id)
    if existing is not None:
        return existing

    title = f"Round {round_num}"
    location_name = venue_name_from_filename(venue_raw)
    date_str = fixture_date.isoformat()  # "YYYY-MM-DD"

    con.execute(
        "INSERT INTO fixtures"
        " (season_id, title, date, location_name, address, timetable,"
        "  travel_instructions)"
        " VALUES (?, ?, ?, ?, '', '[]', '')",
        [season_id, title, date_str, location_name],
    )
    row = con.execute(
        "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
        [season_id, fixture_date],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    print(f"    Created fixture: {title!r} at {location_name!r} ({date_str})")
    return int(row[0])


# ---------------------------------------------------------------------------
# Category normalisation (mirrors src/cli/seed_results.py)
# ---------------------------------------------------------------------------

# Map raw category display names to pyresults category codes.
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

# Gender-dependent mappings: (gender_lower, category_lower) → code.
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

# Column header aliases → internal canonical names (results tables).
HEADER_MAP: dict[str, str] = {
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


def normalise_header(raw: str) -> str:
    """Map a raw PDF column header to an internal canonical name."""
    cleaned = raw.strip().lower()
    return HEADER_MAP.get(cleaned, cleaned)


def normalise_category(raw_category: str, gender: str) -> str:
    """Normalise a raw category string to a pyresults category code.

    Priority:
    1. Exact case-insensitive match against known pyresults codes.
    2. Gender-dependent veteran lookup (e.g. "V40" + "male" → "MV40").
    3. Unambiguous display-name table (e.g. "Senior Men" → "SM").
    4. Return unchanged and print a warning.
    """
    try:
        from pyresults import get_valid_category_codes  # noqa: PLC0415

        valid = get_valid_category_codes()
    except ImportError:
        valid = []

    stripped = raw_category.strip()
    upper = stripped.upper()

    for code in valid:
        if code.upper() == upper:
            return code

    cat_lower = stripped.lower()
    gender_lower = gender.strip().lower()

    gender_mapped = _GENDER_CATEGORY_MAP.get((gender_lower, cat_lower))
    if gender_mapped:
        return gender_mapped

    name_mapped = _CATEGORY_NAME_MAP.get(cat_lower)
    if name_mapped:
        return name_mapped

    print(
        f"  WARNING: unrecognised category '{stripped}' (gender={gender}); "
        "storing as-is.",
        file=sys.stderr,
    )
    return stripped


def normalise_category_heading(heading: str) -> str:
    """Normalise a standings section heading (e.g. 'Senior Men') to a category code.

    Handles PDF heading variants such as:
    - "Senior Mens Individuals" / "Senior Womens Individuals" → SM / SW
    - "U9 Girls Individuals" / "U9 Girls Teams" → U9G
    - "Mens Teams" / "Womens Teams" → SM / SW
    - "Mens Overall" / "Womens Overall" → stored as-is (non-standard combined categories)
    - Veteran headings like "Male Vet 40", "MV40" → MV40
    """
    import re as _re  # noqa: PLC0415

    stripped = heading.strip()

    # Filter out page-level titles (> 6 words almost certainly not a category heading).
    if len(stripped.split()) > 6:
        return stripped

    # Strip trailing " Individuals" or " Teams" — the table classification handles that.
    base = _re.sub(
        r"\s+(?:individuals?|teams?)\s*$", "", stripped, flags=_re.IGNORECASE
    ).strip()

    # Extended heading → category code map.
    # Covers patterns found in OXL standings PDFs.
    _HEADING_MAP: dict[str, str] = {
        **_CATEGORY_NAME_MAP,
        # Possessive / plural variants
        "senior mens": "SM",
        "senior men's": "SM",
        "senior womens": "SW",
        "senior women's": "SW",
        # "Under N" written-out forms (2025-26 PDF format)
        "under 9 boys": "U9B",
        "under 9 girls": "U9G",
        "under 11 boys": "U11B",
        "under 11 girls": "U11G",
        "under 13 boys": "U13B",
        "under 13 girls": "U13G",
        "under 15 boys": "U15B",
        "under 15 girls": "U15G",
        "under 17 men": "U17M",
        "under 17 women": "U17W",
        "under 20 men": "U20M",
        "under 20 women": "U20W",
        # Overall / combined standings (non-standard; stored as human-readable strings).
        "mens overall": "Mens Overall",
        "womens overall": "Womens Overall",
        "men's overall": "Men's Overall",
        "women's overall": "Women's Overall",
        # Short forms used in team tables
        "mens": "SM",
        "womens": "SW",
        "men": "SM",
        "women": "SW",
        # Possessive short forms in team tables (e.g. "U17 Men's")
        "u17 men's": "U17M",
        "u17 women's": "U17W",
        "u20 men's": "U20M",
        "u20 women's": "U20W",
        # Divisional team categories (2025-26 format); stored as-is.
        "men's teams - division 1": "Men's Teams - Division 1",
        "men's teams - division 2": "Men's Teams - Division 2",
        "men's teams - division 3": "Men's Teams - Division 3",
        "women's teams - division 1": "Women's Teams - Division 1",
        "women's teams - division 2": "Women's Teams - Division 2",
        "women's teams - division 3": "Women's Teams - Division 3",
        # Under-age with written-out gender
        "u17 men": "U17M",
        "u17 women": "U17W",
        "u20 men": "U20M",
        "u20 women": "U20W",
        # Veteran written forms
        "male vet 40": "MV40",
        "male vet 50": "MV50",
        "male vet 60": "MV60",
        "male vet 70": "MV70",
        "female vet 40": "WV40",
        "female vet 50": "WV50",
        "female vet 60": "WV60",
        "female vet 70": "WV70",
        "mv40": "MV40",
        "mv50": "MV50",
        "mv60": "MV60",
        "mv70": "MV70",
        "wv40": "WV40",
        "wv50": "WV50",
        "wv60": "WV60",
        "wv70": "WV70",
    }

    # Try the cleaned base (with suffix stripped) first.
    name_mapped = _HEADING_MAP.get(base.lower())
    if name_mapped:
        return name_mapped

    # Fall back to the original stripped heading.
    name_mapped = _HEADING_MAP.get(stripped.lower())
    if name_mapped:
        return name_mapped

    # Infer gender for veteran patterns like "Male V40", "Vet 40 Men".
    lower = base.lower()
    if "male" in lower or "men" in lower or "boy" in lower:
        inferred_gender = "male"
    else:
        inferred_gender = "female"

    for suffix in ("v40", "v50", "v60", "v70"):
        if suffix in lower.replace(" ", "").replace("et", ""):
            mapped = _GENDER_CATEGORY_MAP.get((inferred_gender, suffix))
            if mapped:
                return mapped

    # Fall through: return the base (suffix-stripped) and let the caller warn.
    return base if base else stripped


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def int_or_none(value: str) -> int | None:
    stripped = value.strip()
    return int(stripped) if stripped else None


def str_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
