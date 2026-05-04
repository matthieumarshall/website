"""Migrate historic end-of-season standings from original-website PDFs into DuckDB.

Targets 2023-24, 2024-25, and 2025-26 seasons, whose standings PDFs contain
cumulative individual and/or team standings tables.  Rows are inserted with
``is_imported = true`` so the recalculation pipeline never overwrites them.

Usage
-----
    uv run python scripts/migrate_standings.py \\
        --pdf "data/original_website/files/results/2020-2030/2024-2025/2024-25 OXL Standings After R5.pdf" \\
        --season 2024-2025 \\
        [--type individual|team|auto] \\
        [--dry-run]

Options
-------
--pdf       Path to the standings PDF to import.
--season    Season name that already exists in the database (e.g. "2024-2025").
--type      Force the table type: "individual", "team", or "auto" (default).
            "auto" classifies each table by its column headers.
--dry-run   Parse and print without writing to the database.
--force     Allow import even if is_imported standings already exist for this
            season (will add rather than replace; use with caution).

Column detection
----------------
Individual standings tables are expected to contain columns for: position,
athlete name, club, total score.  Optional: per-round scores (R1…R5).

Team standings tables additionally have a team name / team column and
optionally a team_label (A/B/C).

Category headings
-----------------
pdfplumber extracts page text that typically contains a section heading such as
"Senior Men", "U13 Boys", or "Male Vet 40" just before each table.  The script
parses that heading into a pyresults category code.  If detection fails, a
warning is printed and the raw heading string is stored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required. Run: uv add --optional dev pdfplumber")

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import _migration_helpers as mh  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent

# Headers that identify an individual standings table.
_INDIVIDUAL_REQUIRED_COLS = {"position"}
_INDIVIDUAL_NAME_COLS = {"athlete_name", "name"}
_TEAM_NAME_COLS = {"team", "team_name"}

# Pattern matching round column headers: "R1", "R2", … or "Round 1", "Round 2", …
_ROUND_COL_RE = re.compile(r"^(?:r|round\s*)(\d+)$", re.IGNORECASE)

# Column header aliases for standings tables.
_STANDINGS_HEADER_MAP: dict[str, str] = {
    # Position
    "pos": "position",
    "position": "position",
    "#": "position",
    # Athlete / team name
    "name": "athlete_name",
    "athlete": "athlete_name",
    "athlete name": "athlete_name",
    "athlete_name": "athlete_name",
    "team": "team_name",
    "team name": "team_name",
    "team_name": "team_name",
    # Club
    "club": "club",
    "club/school": "club",
    # Score
    "total": "total_score",
    "total score": "total_score",
    "score": "total_score",
    "points": "total_score",
    "total_score": "total_score",
    # Rounds competed
    "rounds": "rounds_competed",
    "rounds competed": "rounds_competed",
    "competed": "rounds_competed",
    "rounds_competed": "rounds_competed",
    # Team label
    "label": "team_label",
    "team label": "team_label",
    "team_label": "team_label",
    "a/b/c": "team_label",
}


# ---------------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------------


def _normalise_standings_header(raw: str) -> str:
    cleaned = raw.strip().lower()
    if cleaned in _STANDINGS_HEADER_MAP:
        return _STANDINGS_HEADER_MAP[cleaned]
    # Check for round column pattern before giving up.
    m = _ROUND_COL_RE.match(cleaned)
    if m:
        return f"round_{m.group(1)}"
    return cleaned


def _parse_header_row(raw_row: list[str | None]) -> list[str]:
    return [_normalise_standings_header(cell or "") for cell in raw_row]


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------


def _classify_table(headers: list[str]) -> str | None:
    """Return "individual", "team", or None (not a standings table)."""
    header_set = set(headers)

    if _TEAM_NAME_COLS & header_set:
        return "team"

    if _INDIVIDUAL_NAME_COLS & header_set and "position" in header_set:
        return "individual"

    # Weaker fallback: if there's a position and a total_score, guess individual.
    if {"position", "total_score"} <= header_set:
        return "individual"

    return None


# ---------------------------------------------------------------------------
# Category heading extraction
# ---------------------------------------------------------------------------


_PAGE_TITLE_WORDS = frozenset(
    {"league", "standings", "cross", "country", "oxfordshire", "oxl", "results"}
)

# Headings that map directly to themselves (non-standard categories that are
# intentionally stored as-is without a warning).
_PASSTHROUGH_HEADINGS = frozenset(
    {
        "Mens Overall",
        "Womens Overall",
        "Men's Overall",
        "Women's Overall",
        "Men's Teams - Division 1",
        "Men's Teams - Division 2",
        "Men's Teams - Division 3",
        "Women's Teams - Division 1",
        "Women's Teams - Division 2",
        "Women's Teams - Division 3",
    }
)


def _extract_category_headings_from_text(page_text: str) -> list[str]:
    """Return short, bold-like lines from *page_text* that may be section headings.

    pdfplumber cannot directly tell us which text is bold, so we heuristically
    look for short capitalised lines (1–6 words) that aren't clearly data rows.
    """
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    headings = []
    for line in lines:
        words = line.split()
        if len(words) < 1 or len(words) > 6:
            continue
        # Skip lines that are clearly data (start with a number or contain colons).
        if words[0].isdigit() or ":" in line:
            continue
        # Skip table column header lines.
        if words[0].lower() in (
            "pos",
            "position",
            "#",
            "name",
            "club",
            "total",
            "score",
        ):
            continue
        # Skip page-level titles (e.g. "Oxfordshire Cross Country League Standings 2024-25").
        word_set = {w.lower().rstrip(".,;") for w in words}
        if word_set & _PAGE_TITLE_WORDS:
            continue
        headings.append(line)
    return headings


def _best_heading_for_table(headings: list[str], table_index: int) -> str:
    """Pick the most likely category heading for the *table_index*-th table."""
    if not headings:
        return ""

    # If there is exactly one heading, use it for all tables.
    if len(headings) == 1:
        return headings[0]

    # Try to return the heading at the same index (one heading per table).
    if table_index < len(headings):
        return headings[table_index]

    return headings[-1]


# ---------------------------------------------------------------------------
# Round column extraction
# ---------------------------------------------------------------------------


def _extract_round_scores(
    row_data: Mapping[str, str],
    fixture_order: list[tuple[int, object]],
) -> dict[str, int]:
    """Build fixture_scores JSON from per-round columns in *row_data*.

    Returns a dict keyed by str(fixture_id) with the round score as an int.
    Rounds with empty / non-numeric values are omitted.
    """
    scores: dict[str, int] = {}
    for col, val in row_data.items():
        m = re.match(r"^round_(\d+)$", col)
        if not m:
            continue
        round_num = int(m.group(1))
        if round_num < 1 or round_num > len(fixture_order):
            continue
        val_stripped = val.strip()
        if not val_stripped or not val_stripped.lstrip("-").isdigit():
            continue
        fixture_id = fixture_order[round_num - 1][0]
        scores[str(fixture_id)] = int(val_stripped)
    return scores


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def _parse_standings_pdf(
    pdf_path: Path,
    season_id: int | None,
    fixture_order: list[tuple[int, object]],
    forced_type: str,
) -> tuple[list[dict], list[dict]]:
    """Parse *pdf_path* and return (individual_rows, team_rows).

    Each individual row::

        {
            "season_id": int,
            "category": str,
            "position": int,
            "athlete_name": str,
            "club": str | None,
            "total_score": int,
            "rounds_competed": int,
            "fixture_scores": str,   # JSON
        }

    Each team row additionally has ``team_name`` and ``team_label``.
    """
    individual_rows: list[dict] = []
    team_rows: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            headings = _extract_category_headings_from_text(page_text)
            tables = page.extract_tables()
            if not tables:
                continue

            standings_tables_on_page = 0

            for table_idx, table in enumerate(tables):
                if not table or not table[0]:
                    continue

                headers = _parse_header_row(table[0])
                table_type = (
                    forced_type if forced_type != "auto" else _classify_table(headers)
                )
                if table_type is None:
                    continue  # not a standings table

                raw_heading = _best_heading_for_table(
                    headings, standings_tables_on_page
                )
                standings_tables_on_page += 1

                category = (
                    mh.normalise_category_heading(raw_heading)
                    if raw_heading
                    else f"Unknown_{table_idx}"
                )

                if (
                    raw_heading
                    and category == raw_heading
                    and category not in _PASSTHROUGH_HEADINGS
                ):
                    # heading was not mapped — warn
                    print(
                        f"  WARNING: category heading '{raw_heading}' not mapped; "
                        "storing as-is.",
                        file=sys.stderr,
                    )

                for raw_row in table[1:]:
                    if not raw_row or all(
                        cell is None or not cell.strip() for cell in raw_row
                    ):
                        continue

                    row_data = {
                        headers[i]: (raw_row[i] or "").strip()
                        for i in range(min(len(headers), len(raw_row)))
                    }

                    pos_raw = row_data.get("position", "")
                    if not pos_raw or not pos_raw.lstrip().isdigit():
                        continue  # sub-heading or totals row

                    total_raw = row_data.get("total_score", "")
                    if not total_raw.lstrip("-").isdigit():
                        total_score = 0
                    else:
                        total_score = int(total_raw)

                    fixture_scores = _extract_round_scores(row_data, fixture_order)
                    rounds_competed_raw = row_data.get("rounds_competed", "")
                    if rounds_competed_raw.isdigit():
                        rounds_competed = int(rounds_competed_raw)
                    else:
                        rounds_competed = len(fixture_scores)

                    base = {
                        "season_id": season_id,
                        "category": category,
                        "position": int(pos_raw.strip()),
                        "club": mh.str_or_none(row_data.get("club", "")),
                        "total_score": total_score,
                        "rounds_competed": rounds_competed,
                        "fixture_scores": json.dumps(fixture_scores),
                    }

                    if table_type == "team":
                        team_name = row_data.get("team_name", "")
                        team_label = mh.str_or_none(row_data.get("team_label", ""))

                        # Attempt to parse label from suffix if not an explicit column.
                        if not team_label and team_name:
                            label_m = re.search(r"\b([ABC])\s*$", team_name)
                            if label_m:
                                team_label = label_m.group(1)

                        # Derive club from team_name by stripping A/B/C suffix.
                        club = base["club"]
                        if not club and team_name:
                            club = re.sub(r"\s+[ABC]\s*$", "", team_name).strip()

                        team_rows.append(
                            {
                                **base,
                                "club": club,
                                "team_name": team_name,
                                "team_label": team_label,
                            }
                        )
                    else:
                        athlete_name = row_data.get("athlete_name", "")
                        individual_rows.append({**base, "athlete_name": athlete_name})

    return individual_rows, team_rows


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------


def _insert_individual(
    con,
    rows: list[dict],
    *,
    dry_run: bool,
) -> None:
    if not rows:
        return

    categories = sorted({r["category"] for r in rows})
    print(
        f"  Individual standings: {len(rows)} rows across "
        f"{len(categories)} categories: {categories}"
    )

    if dry_run:
        for r in rows[:5]:
            print(
                f"    [{r['position']}] {r['athlete_name']!r}  cat={r['category']}  "
                f"score={r['total_score']}  rounds={r['rounds_competed']}  "
                f"club={r['club']!r}"
            )
        if len(rows) > 5:
            print(f"    … and {len(rows) - 5} more")
        return

    con.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, true, current_timestamp)",
        [
            [
                r["season_id"],
                r["category"],
                r["position"],
                r["athlete_name"],
                r["club"],
                r["total_score"],
                r["rounds_competed"],
                r["fixture_scores"],
            ]
            for r in rows
        ],
    )


def _insert_team(
    con,
    rows: list[dict],
    *,
    dry_run: bool,
) -> None:
    if not rows:
        return

    categories = sorted({r["category"] for r in rows})
    print(
        f"  Team standings: {len(rows)} rows across "
        f"{len(categories)} categories: {categories}"
    )

    if dry_run:
        for r in rows[:5]:
            print(
                f"    [{r['position']}] {r['team_name']!r} ({r['team_label']})  "
                f"cat={r['category']}  score={r['total_score']}  "
                f"rounds={r['rounds_competed']}  club={r['club']!r}"
            )
        if len(rows) > 5:
            print(f"    … and {len(rows) - 5} more")
        return

    con.executemany(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, true, current_timestamp)",
        [
            [
                r["season_id"],
                r["category"],
                r["position"],
                r["team_name"],
                r["club"],
                r["team_label"],
                r["total_score"],
                r["rounds_competed"],
                r["fixture_scores"],
            ]
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate historic standings from an original-website PDF into DuckDB."
        )
    )
    parser.add_argument(
        "--pdf",
        required=True,
        metavar="PATH",
        help="Path to the standings PDF to import.",
    )
    parser.add_argument(
        "--season",
        required=True,
        metavar="YYYY-YYYY",
        help="Season name that already exists in the database (e.g. '2024-2025').",
    )
    parser.add_argument(
        "--type",
        dest="table_type",
        choices=["individual", "team", "auto"],
        default="auto",
        help=(
            "Force table classification: 'individual', 'team', or 'auto' (default). "
            "Use 'individual' or 'team' when the PDF contains only one type."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print without writing to the database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Allow import even if is_imported standings already exist for this season "
            "(rows are added, not replaced)."
        ),
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")

    if args.dry_run:
        print("DRY RUN — no data will be written to the database.\n")
        con = mh.open_db()
        try:
            _run(
                pdf_path,
                args.season,
                args.table_type,
                con,
                dry_run=True,
                force=args.force,
            )
        finally:
            con.close()
    else:
        con = mh.open_db()
        try:
            _run(
                pdf_path,
                args.season,
                args.table_type,
                con,
                dry_run=False,
                force=args.force,
            )
            con.commit()
        finally:
            con.close()

    print("\nDone.")


def _run(
    pdf_path: Path,
    season_name: str,
    table_type: str,
    con,
    *,
    dry_run: bool,
    force: bool,
) -> None:
    if dry_run:
        row = con.execute(
            "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
        ).fetchone()
        season_id = int(row[0]) if row else None
        id_label = f"id={season_id}" if season_id else "will be created"
    else:
        season_id = mh.create_season_if_missing(con, season_name)
        id_label = f"id={season_id}"
    print(f"Season: {season_name!r} ({id_label})")
    print(f"PDF:    {pdf_path}")

    # Idempotency guard.
    if not force and not dry_run and season_id is not None:
        existing = con.execute(
            "SELECT COUNT(*) FROM individual_standings"
            " WHERE season_id = ? AND is_imported = true",
            [season_id],
        ).fetchone()[0]
        existing_t = con.execute(
            "SELECT COUNT(*) FROM team_standings"
            " WHERE season_id = ? AND is_imported = true",
            [season_id],
        ).fetchone()[0]
        if existing or existing_t:
            sys.exit(
                f"Season '{season_name}' already has is_imported standings "
                f"({existing} individual, {existing_t} team). "
                "Use --force to add more rows anyway."
            )

    if season_id is not None:
        fixture_order = mh.list_fixtures_for_season_ordered(con, season_id)
    else:
        fixture_order: list[tuple[int, object]] = []
    print(
        f"Fixtures in season: {len(fixture_order)} "
        f"(round 1 = fixture_id {fixture_order[0][0] if fixture_order else 'none'})"
    )

    individual_rows, team_rows = _parse_standings_pdf(
        pdf_path,
        season_id,
        cast(list[tuple[int, object]], fixture_order),
        table_type,
    )

    if not individual_rows and not team_rows:
        print(
            "WARNING: No standings tables were extracted from this PDF. "
            "Check that the PDF contains selectable text and that the column "
            "headers match expected patterns.",
            file=sys.stderr,
        )
        return

    _insert_individual(con, individual_rows, dry_run=dry_run)
    _insert_team(con, team_rows, dry_run=dry_run)


if __name__ == "__main__":
    main()
