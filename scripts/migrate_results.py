"""Migrate historic per-round race results from original-website PDFs into DuckDB.

Covers all available seasons back to 1988-89.  Result PDFs follow the naming
convention::

    YYYYMMDD-RndN-VenueName-min.pdf

The date and round number are parsed from the filename.  If the corresponding
season or fixture does not yet exist in the database they are created
automatically.  Each table found in the PDF becomes one ``races`` row; each
data row becomes one ``results`` row.

Usage
-----
    uv run python scripts/migrate_results.py [--season YYYY-YYYY] [--dry-run]

Options
-------
--season    Only migrate one specific season subfolder (e.g. "2021-2022").
            Omit to process all qualifying subdirectories across all decades.
--dry-run   Parse PDFs and print what would be inserted without touching the DB.

Run with --dry-run first to inspect the parsed output before committing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required. Run: uv add --optional dev pdfplumber")

# Make sure the scripts/ sibling modules are importable regardless of cwd.
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import _migration_helpers as mh  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
# Scan the top-level results directory; each subdirectory is a decade folder
# (e.g. "1990-2000") that in turn contains season subdirectories.
_RESULTS_ROOT = _ROOT / "data" / "original_website" / "files" / "results"

# Matches filenames like "20211107-Rnd1-BicesterHeritage-min.pdf".
# Group 1 = date (YYYYMMDD), group 2 = round number, group 3 = venue fragment.
_RESULTS_PDF_RE = re.compile(r"^(\d{8})-Rnd(\d+)-(.+?)-min\.pdf$", re.IGNORECASE)

# Column headers that identify a results table (must contain at least these).
_REQUIRED_RESULT_COLS = {"position", "athlete_name", "time", "category", "gender"}

# Race-name headings that appear in results PDFs as section titles.
# Ordered from most-junior to senior so display_order matches a sensible sort.
_RACE_DISPLAY_ORDER: list[str] = [
    "U9",
    "U11",
    "U13",
    "U15",
    "U17",
    "Men",
    "Women",
    "Seniors",
    "Veterans",
]


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def _infer_race_name_from_text(page_text: str, table_index: int) -> str:
    """Attempt to extract a race/category heading from surrounding page text.

    pdfplumber returns the full page text as a single string.  Section headings
    (e.g. "Men", "Senior Women", "U13 Boys") typically appear as short lines
    immediately before the table data.  We look for the last short, non-numeric
    line before the table area.

    Falls back to "Race <N>" if nothing useful is found.
    """
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    # Find lines that look like race headings: 1–5 words, not all digits/punctuation.
    candidates = []
    for line in lines:
        words = line.split()
        if (
            1 <= len(words) <= 6
            and not all(w.replace(".", "").isdigit() for w in words)
            and not line.startswith(("Pos", "pos", "Position", "#", "Race"))
        ):
            candidates.append(line)

    if candidates:
        return candidates[-1]

    return f"Race {table_index + 1}"


def _parse_header_row(raw_row: list[str | None]) -> list[str]:
    """Normalise a raw table header row into canonical column names."""
    return [mh.normalise_header(cell or "") for cell in raw_row]


def _is_results_table(headers: list[str]) -> bool:
    """Return True if *headers* contain all required results columns."""
    return _REQUIRED_RESULT_COLS.issubset(set(headers))


def _parse_results_pdf(
    pdf_path: Path,
) -> list[dict]:
    """Extract races and their results from *pdf_path*.

    Returns a list of race dicts::

        {
            "name": str,
            "display_order": int,
            "results": [
                {
                    "position": int,
                    "athlete_name": str,
                    "time": str,
                    "category": str,
                    "gender": str,
                    "race_number": int | None,
                    "category_position": int | None,
                    "gender_position": int | None,
                    "club": str | None,
                },
                ...
            ],
        }
    """
    races: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            tables = page.extract_tables()
            if not tables:
                continue

            for table_idx, table in enumerate(tables):
                if not table or not table[0]:
                    continue

                raw_header = table[0]
                headers = _parse_header_row(raw_header)

                if not _is_results_table(headers):
                    continue  # not a results table (e.g. a timetable header)

                race_name = _infer_race_name_from_text(page_text, table_idx)
                results: list[dict] = []

                for raw_row in table[1:]:
                    if not raw_row or all(
                        cell is None or not cell.strip() for cell in raw_row
                    ):
                        continue  # blank separator row

                    row_data = {
                        headers[i]: (raw_row[i] or "").strip()
                        for i in range(min(len(headers), len(raw_row)))
                    }

                    pos_raw = row_data.get("position", "")
                    if not pos_raw or not pos_raw.isdigit():
                        continue  # skip sub-heading or totals rows

                    gender_raw = row_data.get("gender", "")
                    category_raw = row_data.get("category", "")

                    results.append(
                        {
                            "position": int(pos_raw),
                            "athlete_name": row_data.get("athlete_name", ""),
                            "time": row_data.get("time", ""),
                            "category": mh.normalise_category(category_raw, gender_raw),
                            "gender": gender_raw,
                            "race_number": mh.int_or_none(
                                row_data.get("race_number", "")
                            ),
                            "category_position": mh.int_or_none(
                                row_data.get("category_position", "")
                            ),
                            "gender_position": mh.int_or_none(
                                row_data.get("gender_position", "")
                            ),
                            "club": mh.str_or_none(row_data.get("club", "")),
                        }
                    )

                if results:
                    display_order = next(
                        (
                            i
                            for i, kw in enumerate(_RACE_DISPLAY_ORDER)
                            if kw.lower() in race_name.lower()
                        ),
                        len(races),
                    )
                    races.append(
                        {
                            "name": race_name,
                            "display_order": display_order,
                            "results": results,
                        }
                    )

    return races


# ---------------------------------------------------------------------------
# DB insertion
# ---------------------------------------------------------------------------


def _insert_races(
    con,
    fixture_id: int,
    races: list[dict],
    *,
    dry_run: bool,
) -> None:
    """Insert *races* (and their results) into the DB for *fixture_id*."""
    sys.path.insert(0, str(_ROOT / "src"))
    from website import repository  # noqa: PLC0415

    for race in races:
        print(f"    Race: '{race['name']}' ({len(race['results'])} result rows)")
        if dry_run:
            for r in race["results"][:3]:
                print(
                    f"      [{r['position']}] {r['athlete_name']!r}  "
                    f"{r['time']}  {r['category']}  {r['gender']}  club={r['club']!r}"
                )
            if len(race["results"]) > 3:
                print(f"      … and {len(race['results']) - 3} more")
            continue

        race_obj = repository.create_race(
            con, fixture_id, race["name"], race["display_order"]
        )
        for r in race["results"]:
            repository.create_result(
                con,
                race_id=race_obj.id,
                position=r["position"],
                athlete_name=r["athlete_name"],
                time=r["time"],
                category=r["category"],
                gender=r["gender"],
                race_number=r["race_number"],
                category_position=r["category_position"],
                gender_position=r["gender_position"],
                club=r["club"],
            )


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------


def _process_season_dir(
    season_dir: Path,
    season_name: str,
    con,
    *,
    dry_run: bool,
) -> None:
    pdf_files = sorted(season_dir.glob("*.pdf"))
    matching_pdfs = [p for p in pdf_files if _RESULTS_PDF_RE.match(p.name)]

    if not matching_pdfs:
        print(f"  No per-round results PDFs found in {season_name!r} — skipping.")
        return

    # Only resolve/create the season once we know there's data to import.
    if dry_run:
        season_id = con.execute(
            "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
        ).fetchone()
        season_id = int(season_id[0]) if season_id else None
        id_label = f"id={season_id}" if season_id else "will be created"
    else:
        season_id = mh.create_season_if_missing(con, season_name)
        id_label = f"id={season_id}"

    print(f"\nSeason: {season_name!r} ({id_label})")

    for pdf_path in matching_pdfs:
        m = _RESULTS_PDF_RE.match(pdf_path.name)
        assert m is not None  # already matched above  # noqa: S101

        date_str = m.group(1)  # e.g. "20211107"
        round_num = int(m.group(2))  # e.g. 1
        venue_raw = m.group(3)  # e.g. "BicesterHeritage"
        fixture_date = datetime.strptime(date_str, "%Y%m%d").date()

        if dry_run:
            venue_display = mh.venue_name_from_filename(venue_raw)
            print(
                f"\n  PDF: {pdf_path.name}"
                f" → Round {round_num}, {venue_display}, {fixture_date}"
            )
            fixture_id = None
        else:
            assert season_id is not None  # noqa: S101  # type: ignore[assert-type]
            fixture_id = mh.get_or_create_fixture(
                con, season_id, round_num, fixture_date, venue_raw
            )

            if mh.fixture_has_races(con, fixture_id):
                print(
                    f"  SKIP: {pdf_path.name} — fixture {fixture_id} already has "
                    "races (delete them first to re-import)"
                )
                continue

            print(f"\n  PDF: {pdf_path.name} → fixture_id={fixture_id}")

        try:
            races = _parse_results_pdf(pdf_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR parsing {pdf_path.name}: {exc}", file=sys.stderr)
            continue

        if not races:
            print("  WARNING: No results tables found in this PDF.")
            continue

        if fixture_id is not None:
            _insert_races(con, fixture_id, races, dry_run=dry_run)

    if not dry_run:
        con.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate historic per-round results from original-website PDFs into DuckDB."
        )
    )
    parser.add_argument(
        "--season",
        metavar="YYYY-YYYY",
        help=(
            "Only process this season subfolder (e.g. '2021-2022'). "
            "Omit to process all seasons across all decade directories."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print without writing to the database.",
    )
    args = parser.parse_args()

    if not _RESULTS_ROOT.exists():
        sys.exit(f"Results directory not found: {_RESULTS_ROOT}")

    if args.dry_run:
        print("DRY RUN — no data will be written to the database.\n")

    con = mh.open_db()
    try:
        # Collect (season_dir, season_name) pairs from decade subdirectories.
        season_pairs: list[tuple[Path, str]] = []
        for decade_dir in sorted(_RESULTS_ROOT.iterdir()):
            if not decade_dir.is_dir():
                continue
            for season_dir in sorted(decade_dir.iterdir()):
                if not season_dir.is_dir():
                    continue
                if args.season and season_dir.name != args.season:
                    continue
                season_pairs.append((season_dir, season_dir.name))

        if args.season and not season_pairs:
            sys.exit(
                f"Season directory '{args.season}' not found under {_RESULTS_ROOT}"
            )

        for season_dir, season_name in season_pairs:
            _process_season_dir(season_dir, season_name, con, dry_run=args.dry_run)
    finally:
        con.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
