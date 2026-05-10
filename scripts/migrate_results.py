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
    uv run python scripts/migrate_results.py [--season YYYY-YYYY] [--dry-run] [--force]

Options
-------
--season    Only migrate one specific season subfolder (e.g. "2021-2022").
            Omit to process all qualifying subdirectories across all decades.
--dry-run   Parse PDFs and print what would be inserted without touching the DB.
--force     Replace existing results (default: skip fixtures that already have races).

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
from _import_logger import ImportLogger  # noqa: E402

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
# Constants for text-based PDF parsers (2010-2020 and 2021+ formats)
# ---------------------------------------------------------------------------

# Matches both colon-separated (2021+: MM:SS) and dot-separated (2010-2020: M.SS) times.
_TIME_RE = re.compile(r"^\d{1,2}[:.]\d{2}$")

# Category codes found in OXL results (case-insensitive).
# Includes legacy codes: MM = Mini Minors (≈U11 in pre-2013 results).
_CAT_RE = re.compile(r"^(U9[BbGg]?|U1[1357]|U20|S|V\d+|MM)$", re.IGNORECASE)

# Identifies pages using the 2010-2020 "league header + text block" table format.
_TEXT_BLOCK_LEAGUE_HEADER = re.compile(
    r"Oxford Mail Cross Country League|Oxfordshire Cross Country League",
    re.IGNORECASE,
)

# Splits text blocks into race sections (captures the race title).
_TEXT_BLOCK_RACE_RE = re.compile(r"Race\s+\d+:\s+(.+?)$", re.MULTILINE | re.IGNORECASE)

# Finds the race title on a 2021+ per-page race page.
# Handles en-dash (–) and ASCII hyphen (-).
_PER_PAGE_RACE_TITLE_RE = re.compile(r"Round\s+\d+\s*[–\-]\s+(.+?)$", re.MULTILINE)

# Detects whether a Round title text is an actual race name (U9, U11, Men, Women,
# etc.) rather than a venue name (e.g. "Bicester Heritage, Bicester").
# 2019-2020 Rounds 1-4 put the venue in the title line; the race name follows on
# the very next line.
_IS_RACE_NAME_RE = re.compile(
    r"^(U9|U1[1357]|U20|Senior|Veteran|Men\b|Women\b|Junior|Mixed)\b",
    re.IGNORECASE,
)

# Detects the start of a new result in a potentially two-column 2021+ line.
# A result starts where digits are followed directly by an uppercase letter
# that begins the athlete's surname (which must be followed by a comma later).
# Requires the digits are NOT preceded by a letter or colon (avoids matching
# inside times like "6:07" or club codes like "AC").
_RESULT_SEGMENT_START = re.compile(r"(?<![A-Za-z:])(\d{1,3})(?=[A-Z][a-z\'\-])")


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
    """Normalise a raw table header row into canonical column names.

    Args:
        raw_row: List of header cell strings (may contain None values).

    Returns:
        List of normalized header names.
    """
    return [mh.normalise_header(cell or "") for cell in raw_row]


def _is_results_table(headers: list[str]) -> bool:
    """Return True if *headers* contain all required results columns.

    Args:
        headers: List of normalized column header names.

    Returns:
        True if this appears to be a results table, False otherwise.
    """
    return _REQUIRED_RESULT_COLS.issubset(set(headers))


# ---------------------------------------------------------------------------
# Text-based parsing helpers (2010-2020 and 2021+ formats)
# ---------------------------------------------------------------------------


def _infer_gender(title: str) -> str:
    """Return 'Male', 'Female', or '' from a race title string.

    Returns '' for mixed-gender races (e.g. 'U9 Boys & Girls') so that
    individual category suffixes (U9b / U9g) can determine each athlete's gender.
    """
    t = title.lower()
    has_female = bool(re.search(r"\b(girl|girls|woman|women|ladies|female)\b", t))
    has_male = bool(re.search(r"\b(boy|boys|man|men|male)\b", t))
    if has_female and has_male:
        return ""  # mixed-gender race
    if has_female:
        return "Female"
    if has_male:
        return "Male"
    return ""


def _display_order_for_race(race_name: str) -> int:
    """Return a display-order index for *race_name* by keyword match."""
    return next(
        (
            i
            for i, kw in enumerate(_RACE_DISPLAY_ORDER)
            if kw.lower() in race_name.lower()
        ),
        len(_RACE_DISPLAY_ORDER),
    )


def _parse_2010_result_line(
    line: str, default_cat: str, default_gender: str
) -> dict | None:
    """Parse one result line from a 2010-2020 text-block PDF.

    Expected format (space-separated)::

        {pos} {FirstName ...} {ClubCode} [{Category}] [{Time as M.SS}]

    Category and time are both optional; they fall back to the defaults
    derived from the race-section heading.

    Returns a result dict or None when the line is not a valid result.
    """
    words = line.split()
    if len(words) < 3 or not words[0].isdigit():
        return None

    position = int(words[0])
    words = words[1:]

    # Peel off time from right end (dot-separated: M.SS or MM.SS).
    time_val = ""
    if words and re.match(r"^\d{1,2}\.\d{2}$", words[-1]):
        time_val = words[-1]
        words = words[:-1]

    # Peel off category from right end.
    category = default_cat
    if words and _CAT_RE.match(words[-1]):
        category = words[-1].upper()
        words = words[:-1]

    # Remaining last word is the club code; everything before it is the name.
    if not words:
        return None
    club = words[-1]
    name = " ".join(words[:-1])
    if not name:
        return None

    # Determine gender; U9G/U9g suffix overrides the race-level default.
    # Plain U9 (no suffix) is treated as male in mixed-gender races where the
    # default_gender is '' (2010-2016 era used 'U9' for boys, 'U9g' for girls).
    gender = default_gender
    cat_up = category.upper()
    if cat_up == "U9G":
        gender = "Female"
    elif cat_up in ("U9B", "U9") and not default_gender:
        gender = "Male"

    normalized_cat = re.sub(r"^U9[BGg]$", "U9", cat_up, flags=re.IGNORECASE)

    return {
        "position": position,
        "athlete_name": name,
        "time": time_val,
        "category": normalized_cat or default_cat,
        "gender": gender or "Unknown",
        "club": club,
        "race_number": None,
        "category_position": None,
        "gender_position": None,
    }


def _split_2021_line(line: str) -> list[str]:
    """Split a potentially two-column 2021+ result line into segments.

    In the two-column PDF layout pdfplumber merges both columns into a single
    text line, e.g.::

        "1Eyre, Annie Banbury Harriers AC U11 6:07 31Smith, John Rad U11 7:15"

    Each result segment starts where position digits are followed directly by
    an uppercase letter (the start of the athlete's surname).
    """
    starts = [m.start() for m in _RESULT_SEGMENT_START.finditer(line)]
    if not starts:
        return []
    segments = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(line)
        seg = line[start:end].strip()
        if seg:
            segments.append(seg)
    return segments


def _parse_2021_result_segment(segment: str, default_gender: str) -> dict | None:
    """Parse a single result segment from a 2021+ per-page PDF.

    Segment format (position digits run directly into the surname)::

        {pos}{LastName, FirstName} {Club words...} {Category} [{Time as MM:SS}]

    Returns a result dict or None if the segment cannot be parsed.
    """
    segment = segment.strip()

    # Extract position (leading digits before the surname).
    pos_m = re.match(r"^(\d{1,3})", segment)
    if not pos_m:
        return None
    position = int(pos_m.group(1))
    remainder = segment[pos_m.end() :]

    # Name has "LastName, FirstName" format; split on first comma.
    if "," not in remainder:
        return None
    last_part, after_comma = remainder.split(",", 1)
    last_name = last_part.strip()
    words = after_comma.strip().split()
    if not words:
        return None

    first_name = words[0]
    words = words[1:]  # Club... Category [Time]

    # Strip time from right (colon-separated: M:SS or MM:SS).
    time_val = ""
    if words and re.match(r"^\d{1,2}:\d{2}$", words[-1]):
        time_val = words[-1]
        words = words[:-1]

    # Category is now the last token.
    if not words or not _CAT_RE.match(words[-1]):
        return None
    category = words[-1].upper()
    club = " ".join(words[:-1]) if len(words) > 1 else None

    # Determine gender from category suffix; fall back to race-level default.
    gender = default_gender
    if category == "U9G":
        gender = "Female"
    elif category == "U9B" and not default_gender:
        gender = "Male"

    normalized_cat = re.sub(r"^U9[BGg]$", "U9", category, flags=re.IGNORECASE)

    return {
        "position": position,
        "athlete_name": f"{last_name}, {first_name}",
        "time": time_val,
        "category": normalized_cat,
        "gender": gender or "Unknown",
        "club": club,
        "race_number": None,
        "category_position": None,
        "gender_position": None,
    }


def _parse_text_block_pdf(pdf_path: Path) -> list[dict]:
    """Parse a 2010-2020 format PDF.

    These PDFs have one large table per page where:
    - Row 0: league/fixture title header
    - Row 1: multi-race text block (may span two cells for two-column layout)
    - Row 2: page footer URL

    The text block contains all race results as plain text separated by
    ``===`` dividers, with sub-sections ``Race N: {title}`` and
    ``Individual Results``.
    """
    races: list[dict] = []

    # Collect text blocks across all pages (races can span page boundaries).
    text_chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            t = tables[0]
            if not t or not t[0] or not _TEXT_BLOCK_LEAGUE_HEADER.search(t[0][0] or ""):
                continue
            if len(t) < 2:
                continue
            row = t[1]
            cell0 = row[0] or ""
            cell1 = row[1] if len(row) > 1 and row[1] else ""
            if cell0:
                text_chunks.append(cell0)
            if cell1:
                text_chunks.append(cell1)

    if not text_chunks:
        return races

    combined = "\n".join(text_chunks)

    # Split into race sections using "Race N: title" markers.
    markers = list(_TEXT_BLOCK_RACE_RE.finditer(combined))
    for i, marker in enumerate(markers):
        race_name = marker.group(1).strip()
        body_start = marker.end()
        body_end = markers[i + 1].start() if i + 1 < len(markers) else len(combined)
        body = combined[body_start:body_end]

        # Only process Individual Results sub-sections.
        ind_m = re.search(r"Individual\s+Results\s*\n[- ]+\n?", body, re.IGNORECASE)
        if not ind_m:
            continue

        results_text = body[ind_m.end() :]
        # Stop before Team Results or a section separator.
        stop_m = re.search(r"(?:Team\s+Results|={3,})", results_text, re.IGNORECASE)
        if stop_m:
            results_text = results_text[: stop_m.start()]

        gender = _infer_gender(race_name)
        cat_m = re.search(r"\b(U9|U11|U13|U15|U17|U20)\b", race_name, re.IGNORECASE)
        default_cat = cat_m.group(1).upper() if cat_m else "S"

        results: list[dict] = []
        for line in results_text.splitlines():
            line = line.strip()
            if not line or re.match(r"^[=\-]+$", line):
                break
            r = _parse_2010_result_line(line, default_cat, gender)
            if r:
                results.append(r)

        if results:
            races.append(
                {
                    "name": race_name,
                    "display_order": _display_order_for_race(race_name),
                    "results": results,
                }
            )

    return races


# Lines to skip in 2021+ per-page PDFs (headers, footers, metadata).
_PER_PAGE_SKIP_RE = re.compile(
    r"^\d{4}[-/]\d{4}\s"  # "2021-2022 Oxfordshire..." season header
    r"|^(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b"
    r"|^Round\s+\d+\s*[–\-]"  # race title line (already extracted)
    r"|^Pos\s+Name\b"  # column header row
    r"|^Race\s+Distance\b"  # distance info
    r"|^http"  # URL footer
    r"|^Page\s+\d+\b",  # "Page N" standalone footer
    re.IGNORECASE,
)


def _parse_per_page_pdf(pdf_path: Path) -> list[dict]:
    """Parse a 2021+ format PDF where each page (after the cover) is one race.

    Pages that are summary/position tables are skipped.  Each race page has:
    - A "Round N – Race Name" title line
    - A "Pos Name Club Cat Time" column-header line (text only, not a table)
    - One or two columns of result lines in the format
      ``{pos}{LastName, FirstName} {Club...} {Cat} [{Time}]``

    When two result columns are present pdfplumber merges them into a single
    text line; ``_split_2021_line`` separates them.
    """
    races: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # 2021+ race pages have no detectable tables.
            if page.extract_tables():
                continue

            text = page.extract_text() or ""
            if not text.strip():
                continue

            title_m = _PER_PAGE_RACE_TITLE_RE.search(text)
            if not title_m:
                continue

            race_title = title_m.group(1).strip()
            # Skip summary/leading-positions pages.
            if re.search(
                r"summary|positions?\s+summary|leading\s+fixture",
                race_title,
                re.IGNORECASE,
            ):
                continue

            # 2019-2020 early rounds put the venue in the "Round N – X" header
            # (e.g. "Round 1 – Bicester Heritage, Bicester") with the actual
            # race name on the very next non-blank line.  Detect this by
            # checking whether the extracted title looks like a race category.
            if not _IS_RACE_NAME_RE.match(race_title):
                for candidate in text[title_m.end() :].splitlines():
                    candidate = candidate.strip()
                    if not candidate:
                        continue
                    if _PER_PAGE_SKIP_RE.match(candidate):
                        continue
                    if re.match(r"^Race\s+Distance\b", candidate, re.IGNORECASE):
                        continue
                    if _IS_RACE_NAME_RE.match(candidate):
                        race_title = candidate
                    break

            gender = _infer_gender(race_title)
            results: list[dict] = []

            for line in text.splitlines():
                line = line.strip()
                if not line or _PER_PAGE_SKIP_RE.match(line):
                    continue
                for segment in _split_2021_line(line):
                    r = _parse_2021_result_segment(segment, gender)
                    if r:
                        results.append(r)

            if results:
                races.append(
                    {
                        "name": race_title,
                        "display_order": _display_order_for_race(race_title),
                        "results": results,
                    }
                )

    return races


# ---------------------------------------------------------------------------
# Main PDF entry point
# ---------------------------------------------------------------------------


def _parse_results_pdf(
    pdf_path: Path,
) -> list[dict]:
    """Extract races and their results from *pdf_path*.

    Uses the decade directory name for fast format detection before calling
    any expensive PDF parsing operations:
    - ``2020-2030/``: 2021+ per-page format (one race per page, text-only)
    - ``2010-2020/``: 2010-2020 text-block format (race sections in tables)
    - Older directories: scanned/garbled PDFs - skip without parsing.

    Falls back to the columnar table format (future-proofing) if neither
    text-based format returns results.

    Returns an empty list when no results are found.
    """
    path_str = str(pdf_path)

    # Fast path: skip pre-2010 PDFs entirely (scanned paper / garbled OCR).
    if "2020-2030" in path_str:
        races = _parse_per_page_pdf(pdf_path)
        if races:
            return races
        # Columnar fallback in case format changes in a future season.
        return _parse_columnar_pdf(pdf_path)

    if "2010-2020" in path_str:
        races = _parse_text_block_pdf(pdf_path)
        if races:
            return races
        # 2019-2020 switched to the per-page format (same as 2021+) while
        # still living in the 2010-2020 directory tree.
        races = _parse_per_page_pdf(pdf_path)
        if races:
            return races
        return _parse_columnar_pdf(pdf_path)

    # Pre-2010 directories (1987-1990, 1990-2000, 2000-2010) contain scanned
    # or garbled OCR PDFs that cannot be parsed reliably.  Skip them.
    return []


def _parse_columnar_pdf(pdf_path: Path) -> list[dict]:
    """Try to parse *pdf_path* as a columnar results table.

    Looks for tables whose first row contains the required column headers
    (Pos / Name / Time / Category / Gender).  This format is used by some
    older computer-generated PDFs.

    Returns an empty list when no matching tables are found.
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
                    races.append(
                        {
                            "name": race_name,
                            "display_order": _display_order_for_race(race_name),
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
    force: bool = False,
    logger: ImportLogger | None = None,
) -> None:
    """Insert *races* (and their results) into the DB for *fixture_id*.

    Args:
        con: DuckDB connection.
        fixture_id: ID of the fixture to insert races for.
        races: List of parsed race dicts from _parse_results_pdf.
        dry_run: If True, do not write to database.
        force: If True, replace existing results; if False, skip duplicates.
        logger: Optional ImportLogger for structured logging.
    """
    sys.path.insert(0, str(_ROOT / "src"))
    from website import repository  # noqa: PLC0415

    for race in races:
        print(f"    Race: '{race['name']}' ({len(race['results'])} result rows)")
        if logger:
            logger.info(
                "race_parse",
                race_name=race["name"],
                result_count=len(race["results"]),
            )

        if dry_run:
            for r in race["results"][:3]:
                print(
                    f"      [{r['position']}] {r['athlete_name']!r}  "
                    f"{r['time']}  {r['category']}  {r['gender']}  club={r['club']!r}"
                )
            if len(race["results"]) > 3:
                print(f"      ... and {len(race['results']) - 3} more")
            continue

        race_obj = repository.create_race(
            con, fixture_id, race["name"], race["display_order"]
        )

        skipped = 0
        inserted = 0

        for r in race["results"]:
            # Check for duplicates if not forcing
            if not force and mh.result_exists(
                con, race_obj.id, r["athlete_name"], r["time"]
            ):
                if logger:
                    logger.info(
                        "result_skip",
                        reason="duplicate",
                        athlete=r["athlete_name"],
                    )
                skipped += 1
                continue

            try:
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
                inserted += 1
                if logger:
                    logger.info(
                        "result_insert",
                        athlete=r["athlete_name"],
                        time=r["time"],
                    )
            except Exception as exc:  # noqa: BLE001
                if logger:
                    logger.error(
                        "result_insert_failed",
                        athlete=r["athlete_name"],
                        error=str(exc),
                    )
                raise

        if skipped > 0:
            print(f"      Skipped {skipped} duplicate results")
        print(f"      Inserted {inserted} new results")


def _copy_pdf_to_uploads(pdf_path: Path, fixture_id: int) -> str:
    """Copy a results PDF from data/original_website to data/uploads/results/{fixture_id}/.

    Returns the relative path (relative to data/uploads) where the PDF was stored.
    E.g. "results/123/20240101-Rnd1-Venue-min.pdf"
    """
    uploads_results_dir = _ROOT / "data" / "uploads" / "results" / str(fixture_id)
    uploads_results_dir.mkdir(parents=True, exist_ok=True)

    dest_path = uploads_results_dir / pdf_path.name
    dest_path.write_bytes(pdf_path.read_bytes())

    # Return relative path from data/uploads
    return str(dest_path.relative_to(_ROOT / "data" / "uploads")).replace("\\", "/")


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------


def _process_season_dir(
    season_dir: Path,
    season_name: str,
    con,
    *,
    dry_run: bool,
    force: bool = False,
    logger: ImportLogger | None = None,
) -> None:
    """Process all result PDFs in a season directory.

    Args:
        season_dir: Path to the season directory.
        season_name: Name of the season (e.g. "2021-2022").
        con: DuckDB connection.
        dry_run: If True, do not write to database.
        force: If True, replace existing results.
        logger: Optional ImportLogger for structured logging.
    """
    pdf_files = sorted(season_dir.glob("*.pdf"))
    matching_pdfs = [p for p in pdf_files if _RESULTS_PDF_RE.match(p.name)]

    if not matching_pdfs:
        print(f"  No per-round results PDFs found in {season_name!r} - skipping.")
        if logger:
            logger.info(
                "season_skip",
                season=season_name,
                reason="no_pdfs",
            )
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
        if logger:
            logger.info(
                "season_created",
                season=season_name,
                season_id=season_id,
            )

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
                f" -> Round {round_num}, {venue_display}, {fixture_date}"
            )
            fixture_id = None
        else:
            assert season_id is not None  # noqa: S101  # type: ignore[assert-type]
            fixture_id = mh.get_or_create_fixture(
                con, season_id, round_num, fixture_date, venue_raw
            )

            if mh.fixture_has_races(con, fixture_id) and not force:
                if logger:
                    logger.info(
                        "fixture_skip",
                        reason="already_has_races",
                        fixture_id=fixture_id,
                    )
                print(
                    f"  SKIP: {pdf_path.name} — fixture {fixture_id} already has "
                    "races (use --force to replace)"
                )
                continue

            if logger:
                logger.info(
                    "pdf_process",
                    filename=pdf_path.name,
                    fixture_id=fixture_id,
                )

            # Copy the PDF to data/uploads/results/{fixture_id}/ and store the relative path.
            # This allows the website to serve the PDF and offer download links.
            source_rel = _copy_pdf_to_uploads(pdf_path, fixture_id)
            sys.path.insert(0, str(_ROOT / "src"))
            from website import repository as _repo  # noqa: PLC0415

            _repo.set_fixture_source_pdf(con, fixture_id, source_rel)

            print(f"\n  PDF: {pdf_path.name} -> fixture_id={fixture_id}")

        try:
            races = _parse_results_pdf(pdf_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR parsing {pdf_path.name}: {exc}", file=sys.stderr)
            if logger:
                logger.error(
                    "pdf_parse_failed",
                    filename=pdf_path.name,
                    error=str(exc),
                )
            continue

        if not races:
            print("  WARNING: No results tables found in this PDF.")
            if logger:
                logger.warning(
                    "pdf_no_tables",
                    filename=pdf_path.name,
                )
            continue

        if fixture_id is not None:
            _insert_races(
                con, fixture_id, races, dry_run=dry_run, force=force, logger=logger
            )

    if not dry_run:
        con.commit()


def main() -> None:
    """Main entry point for the results migration script.

    Parses command-line arguments and processes season directories,
    extracting results data from PDFs and inserting into the DuckDB database.
    """
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing results (default: skip fixtures with existing races).",
    )
    args = parser.parse_args()

    if not _RESULTS_ROOT.exists():
        sys.exit(f"Results directory not found: {_RESULTS_ROOT}")

    if args.dry_run:
        print("DRY RUN - no data will be written to the database.\n")

    # Initialize logger for structured output
    logger = ImportLogger()

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
            _process_season_dir(
                season_dir,
                season_name,
                con,
                dry_run=args.dry_run,
                force=args.force,
                logger=logger,
            )
    finally:
        con.close()

    # Print summary
    print("\n" + logger.summary())
    print("\nDone.")


if __name__ == "__main__":
    main()
