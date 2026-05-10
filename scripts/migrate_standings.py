"""Migrate historic end-of-season standings from original-website PDFs into DuckDB.

Targets 2023-24, 2024-25, and 2025-26 seasons, whose standings PDFs contain
cumulative individual and/or team standings tables.  Rows are inserted with
``is_imported = true`` so the recalculation pipeline never overwrites them.

Usage
-----
    # Single PDF import:
    uv run python scripts/migrate_standings.py \\
        --pdf "data/original_website/files/results/2020-2030/2024-2025/2024-25 OXL Standings After R5.pdf" \\
        --season 2024-2025 \\
        [--type individual|team|auto] \\
        [--dry-run] \\
        [--force]

    # Directory-based import (auto-discover PDFs):
    uv run python scripts/migrate_standings.py \\
        data/original_website/files/results/2020-2030/ \\
        [--dry-run] \\
        [--force] \\
        [--season YYYY-YYYY]

Options
-------
--pdf       Path to a single standings PDF to import.
--season    Season name (e.g. "2024-2025").
            When used with --pdf, must match the PDF.
            When used with directory mode, filter to only this season.
--type      Force the table type: "individual", "team", or "auto" (default).
            "auto" classifies each table by its column headers.
--dry-run   Parse and print without writing to the database.
--force     Replace existing is_imported standings for the season.
            Without --force, import fails if standings already exist.

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
from datetime import datetime
from pathlib import Path
from typing import cast

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required. Run: uv add --optional dev pdfplumber")

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import _migration_helpers as mh  # noqa: E402
from _import_logger import ImportLogger  # noqa: E402

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
    """Normalize a standings table header to canonical form.

    Maps common variations (e.g. "pos", "Position", "#") to standard names
    like "position". Recognizes round columns (R1, Round 1) as round_N.

    Args:
        raw: Raw header string from PDF.

    Returns:
        Normalized header name.
    """
    cleaned = raw.strip().lower()
    if cleaned in _STANDINGS_HEADER_MAP:
        return _STANDINGS_HEADER_MAP[cleaned]
    # Check for round column pattern before giving up.
    m = _ROUND_COL_RE.match(cleaned)
    if m:
        return f"round_{m.group(1)}"
    return cleaned


def _parse_header_row(raw_row: list[str | None]) -> list[str]:
    """Parse and normalize a header row from a standings table.

    Args:
        raw_row: List of raw header strings from PDF.

    Returns:
        List of normalized header names.
    """
    return [_normalise_standings_header(cell or "") for cell in raw_row]


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------


def _classify_table(headers: list[str]) -> str | None:
    """Classify a PDF table as individual or team standings.

    Returns "individual", "team", or None (not a standings table).

    Args:
        headers: Normalized header names from the table.

    Returns:
        "individual", "team", or None.
    """
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
    """Extract potential category headings from PDF page text.

    pdfplumber cannot directly tell us which text is bold, so we heuristically
    look for short capitalised lines (1–6 words) that aren't clearly data rows.

    Args:
        page_text: Page text extracted from PDF.

    Returns:
        List of potential category heading strings.
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
    """Pick the most likely category heading for the table_index-th table.

    Args:
        headings: List of extracted heading strings.
        table_index: Index of the table in the current page.

    Returns:
        The best matching heading string, or empty string if none found.
    """
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
    """Build fixture_scores JSON from per-round columns in row_data.

    Extracts scores from columns named round_1, round_2, etc. and maps them
    to fixture IDs based on fixture_order.

    Returns a dict keyed by str(fixture_id) with the round score as an int.
    Rounds with empty / non-numeric values are omitted.

    Args:
        row_data: Dictionary of normalized column name to value for this row.
        fixture_order: List of (fixture_id, date) tuples in season order.

    Returns:
        Dictionary mapping str(fixture_id) -> int(score).
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
    """Parse standings PDF and return (individual_rows, team_rows).

    Each individual row includes:
    - season_id, category, position, athlete_name, club
    - total_score, rounds_competed, fixture_scores (JSON)

    Each team row additionally has team_name and team_label.

    Args:
        pdf_path: Path to the PDF file.
        season_id: Season ID to store, or None.
        fixture_order: List of (fixture_id, date) tuples in order.
        forced_type: "individual", "team", or "auto" classification.

    Returns:
        Tuple of (individual_rows_list, team_rows_list).
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
    logger: ImportLogger | None = None,
) -> None:
    """Insert individual standings rows into the database.

    Args:
        con: DuckDB connection.
        rows: List of individual standings dictionaries.
        dry_run: If True, print without writing.
        logger: Optional ImportLogger for structured logging.
    """
    if not rows:
        return

    categories = sorted({r["category"] for r in rows})
    msg = (
        f"  Individual standings: {len(rows)} rows across "
        f"{len(categories)} categories: {categories}"
    )
    print(msg)
    if logger:
        logger.info("standings_individual", count=len(rows), categories=len(categories))

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
    logger: ImportLogger | None = None,
) -> None:
    """Insert team standings rows into the database.

    Args:
        con: DuckDB connection.
        rows: List of team standings dictionaries.
        dry_run: If True, print without writing.
        logger: Optional ImportLogger for structured logging.
    """
    if not rows:
        return

    categories = sorted({r["category"] for r in rows})
    msg = (
        f"  Team standings: {len(rows)} rows across "
        f"{len(categories)} categories: {categories}"
    )
    print(msg)
    if logger:
        logger.info("standings_team", count=len(rows), categories=len(categories))

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


def _run(
    pdf_path: Path,
    season_name: str,
    table_type: str,
    con,
    *,
    dry_run: bool,
    force: bool,
    logger: ImportLogger | None = None,
) -> None:
    """Run standings import for a single PDF.

    Args:
        pdf_path: Path to the standings PDF.
        season_name: Season name to import for.
        table_type: "individual", "team", or "auto".
        con: DuckDB connection.
        dry_run: If True, parse without writing.
        force: If True, replace existing standings.
        logger: Optional ImportLogger for structured logging.
    """
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
            msg = (
                f"Season '{season_name}' already has is_imported standings "
                f"({existing} individual, {existing_t} team). "
                "Use --force to replace."
            )
            print(msg, file=sys.stderr)
            if logger:
                logger.warning(
                    "standings_exists",
                    season_name=season_name,
                    existing_ind=existing,
                    existing_team=existing_t,
                )
            sys.exit(1)

    # Force delete if requested
    if force and not dry_run and season_id is not None:
        con.execute(
            "DELETE FROM individual_standings WHERE season_id = ? AND is_imported = true",
            [season_id],
        )
        con.execute(
            "DELETE FROM team_standings WHERE season_id = ? AND is_imported = true",
            [season_id],
        )
        if logger:
            logger.info("standings_force_delete", season_id=season_id)

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
        msg = (
            "WARNING: No standings tables were extracted from this PDF. "
            "Check that the PDF contains selectable text and that the column "
            "headers match expected patterns."
        )
        print(msg, file=sys.stderr)
        if logger:
            logger.warning("standings_no_tables_found", pdf_path=str(pdf_path))
        return

    _insert_individual(con, individual_rows, dry_run=dry_run, logger=logger)
    _insert_team(con, team_rows, dry_run=dry_run, logger=logger)

    if logger:
        logger.info(
            "standings_import_complete",
            season_id=season_id,
            individual_count=len(individual_rows),
            team_count=len(team_rows),
        )


def _process_standings_directory(
    directory: Path,
    con,
    *,
    dry_run: bool,
    force: bool,
    season_filter: str | None = None,
    logger: ImportLogger | None = None,
) -> None:
    """Process all standings PDFs in a directory tree (directory-based import).

    Looks for PDFs in season subdirectories and imports them.
    Directory structure should be: {directory}/{YYYY-YYYY}/{filename}.pdf

    Args:
        directory: Root directory containing season folders.
        con: DuckDB connection.
        dry_run: If True, parse without writing.
        force: If True, replace existing standings.
        season_filter: Optional season name to filter (e.g. "2024-2025").
        logger: Optional ImportLogger for structured logging.
    """
    if not directory.is_dir():
        print(f"ERROR: Directory not found: {directory}", file=sys.stderr)
        return

    # Find all season directories (named like 2024-2025)
    season_dirs = sorted(
        [d for d in directory.iterdir() if d.is_dir() and "-" in d.name]
    )

    if not season_dirs:
        print(f"No season directories found in {directory}", file=sys.stderr)
        return

    total_processed = 0

    for season_dir in season_dirs:
        season_name = season_dir.name

        # Filter by season if requested
        if season_filter and season_name != season_filter:
            continue

        # Find PDFs in this season directory
        pdfs = sorted(season_dir.glob("*.pdf"))
        if not pdfs:
            if logger:
                logger.info(
                    "standings_season_skip", season_name=season_name, reason="no_pdfs"
                )
            continue

        print(f"\nSeason: {season_name}")
        if logger:
            logger.info(
                "standings_season_start", season_name=season_name, pdf_count=len(pdfs)
            )

        for pdf_path in pdfs:
            print(f"  Processing: {pdf_path.name}")
            try:
                _run(
                    pdf_path,
                    season_name,
                    "auto",
                    con,
                    dry_run=dry_run,
                    force=force,
                    logger=logger,
                )
                total_processed += 1
            except Exception as e:
                msg = f"    ERROR processing {pdf_path.name}: {e}"
                print(msg, file=sys.stderr)
                if logger:
                    logger.error(
                        "standings_pdf_error", pdf_path=str(pdf_path), error=str(e)
                    )

        if not dry_run:
            con.commit()

    print(f"\nProcessed {total_processed} standings PDFs")
    if logger:
        logger.info("standings_directory_complete", total_processed=total_processed)


def main() -> None:
    """Main entry point with argument parsing.

    Supports two modes:
    1. Single PDF: --pdf <path> --season <name> [--type auto|individual|team]
    2. Directory: <directory> [--season filter]

    Both modes support --dry-run and --force flags.
    """
    parser = argparse.ArgumentParser(
        description="Migrate historic standings from original-website PDFs into DuckDB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Positional argument for directory mode
    parser.add_argument(
        "directory",
        nargs="?",
        metavar="DIRECTORY",
        help="Directory containing season folders with standings PDFs (directory mode).",
    )

    parser.add_argument(
        "--pdf",
        metavar="PATH",
        help="Path to a single standings PDF to import (single-PDF mode).",
    )
    parser.add_argument(
        "--season",
        metavar="YYYY-YYYY",
        help=(
            "Season name (e.g. '2024-2025'). "
            "Required in single-PDF mode; optional in directory mode (to filter)."
        ),
    )
    parser.add_argument(
        "--type",
        dest="table_type",
        choices=["individual", "team", "auto"],
        default="auto",
        help=(
            "Force table classification: 'individual', 'team', or 'auto' (default). "
            "(Single-PDF mode only)"
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
        help="Replace existing is_imported standings for this season.",
    )
    args = parser.parse_args()

    # Determine mode and validate arguments
    if args.pdf:
        # Single-PDF mode
        if not args.season:
            parser.error("--season is required when using --pdf")
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            sys.exit(f"PDF not found: {pdf_path}")

        # Initialize logger
        timestamp = datetime.now().isoformat()
        log_file = (
            Path("data") / f"standings_import_{timestamp.replace(':', '-')}.jsonl"
        )
        logger = ImportLogger(log_file=log_file)

        print(f"{'DRY RUN' if args.dry_run else 'IMPORT'} — Standings")
        if args.dry_run:
            print("No data will be written to the database.\n")

        con = mh.open_db()
        try:
            _run(
                pdf_path,
                args.season,
                args.table_type,
                con,
                dry_run=args.dry_run,
                force=args.force,
                logger=logger,
            )
            if not args.dry_run:
                con.commit()
        finally:
            con.close()

        print(f"\n{logger.summary()}")
        logger.write_summary(
            Path("data") / f"standings_import_summary_{timestamp.replace(':', '-')}.txt"
        )

    elif args.directory:
        # Directory mode
        directory = Path(args.directory)

        # Initialize logger
        timestamp = datetime.now().isoformat()
        log_file = (
            Path("data")
            / f"standings_directory_import_{timestamp.replace(':', '-')}.jsonl"
        )
        logger = ImportLogger(log_file=log_file)

        print(f"{'DRY RUN' if args.dry_run else 'IMPORT'} — Standings from directory")
        if args.dry_run:
            print("No data will be written to the database.\n")

        con = mh.open_db()
        try:
            _process_standings_directory(
                directory,
                con,
                dry_run=args.dry_run,
                force=args.force,
                season_filter=args.season,
                logger=logger,
            )
            if not args.dry_run:
                con.commit()
        finally:
            con.close()

        print(f"\n{logger.summary()}")
        logger.write_summary(
            Path("data")
            / f"standings_directory_import_summary_{timestamp.replace(':', '-')}.txt"
        )

    else:
        parser.error("Either DIRECTORY or --pdf is required")

    print("Done.")


if __name__ == "__main__":
    main()
