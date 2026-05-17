"""Audit all results PDFs to find those with no parseable results table.

For each PDF:
- Attempts to extract tables using pdfplumber
- Reports if no table is found, or if tables don't have expected columns
- Prints the actual headers found so we can extend HEADER_MAP

Usage:
    uv run python scripts/audit_pdfs.py
    uv run python scripts/audit_pdfs.py --verbose       # show all PDFs, not just failures
    uv run python scripts/audit_pdfs.py --season 1989-1990
    uv run python scripts/audit_pdfs.py --show-headers  # show raw headers for failures
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber is required. Run: uv add pdfplumber")

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))
import _migration_helpers as mh  # noqa: E402

_RESULTS_ROOT = (
    Path(__file__).parent.parent / "data" / "original_website" / "files" / "results"
)
_PDF_RE = re.compile(r"^(\d{8})-Rnd(\d+)-(.+?)-min\.pdf$", re.IGNORECASE)
_REQUIRED_COLS = {"position", "athlete_name", "time", "category", "gender"}


def _analyse_pdf(pdf_path: Path) -> dict:
    """Return a dict describing what's inside the PDF."""
    result: dict = {
        "path": pdf_path,
        "pages": 0,
        "raw_tables": 0,
        "recognised_tables": 0,
        "total_result_rows": 0,
        "has_text": False,
        "headers_seen": [],  # list of (raw_row, normalised_row) for every table
        "missing_cols": [],  # required cols absent from each table
        "error": None,
    }
    try:
        with pdfplumber.open(pdf_path) as pdf:
            result["pages"] = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    result["has_text"] = True
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or not table[0]:
                        continue
                    raw_header = table[0]
                    result["raw_tables"] += 1
                    normalised = [mh.normalise_header(c or "") for c in raw_header]
                    result["headers_seen"].append(
                        {
                            "raw": [c or "" for c in raw_header],
                            "normalised": normalised,
                        }
                    )
                    norm_set = set(normalised)
                    missing = _REQUIRED_COLS - norm_set
                    result["missing_cols"].append(missing)
                    if not missing:
                        result["recognised_tables"] += 1
                        # count data rows
                        for row in table[1:]:
                            if row and any(c and c.strip() for c in row):
                                pos = (row[0] or "").strip()
                                if pos.isdigit():
                                    result["total_result_rows"] += 1
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit all results PDFs for parseable tables."
    )
    parser.add_argument("--season", metavar="YYYY-YYYY", help="Only audit this season.")
    parser.add_argument(
        "--verbose", action="store_true", help="Show all PDFs, including successes."
    )
    parser.add_argument(
        "--show-headers",
        action="store_true",
        help="Show raw column headers for failures.",
    )
    args = parser.parse_args()

    # Collect PDFs
    pdfs: list[Path] = []
    for decade_dir in sorted(_RESULTS_ROOT.iterdir()):
        if not decade_dir.is_dir():
            continue
        for season_dir in sorted(decade_dir.iterdir()):
            if not season_dir.is_dir():
                continue
            if args.season and season_dir.name != args.season:
                continue
            for pdf in sorted(season_dir.glob("*.pdf")):
                if _PDF_RE.match(pdf.name):
                    pdfs.append(pdf)

    if not pdfs:
        print(
            f"No PDFs found under {_RESULTS_ROOT}"
            + (f" for season {args.season}" if args.season else "")
        )
        return

    print(f"Auditing {len(pdfs)} PDFs...\n")

    # Tallies
    ok = 0
    no_tables = 0
    wrong_cols = 0
    errors = 0
    scanned_images = 0

    # Track all unique raw header cells seen in failing PDFs
    unknown_headers: dict[str, int] = {}  # raw_cell → count of PDFs it appears in

    for pdf_path in pdfs:
        info = _analyse_pdf(pdf_path)
        season = pdf_path.parent.name
        rel = f"{season}/{pdf_path.name}"

        if info["error"]:
            errors += 1
            print(f"  ERROR   {rel}")
            print(f"          {info['error']}")
            continue

        if info["recognised_tables"] > 0:
            ok += 1
            if args.verbose:
                print(
                    f"  OK ({info['recognised_tables']} tables, {info['total_result_rows']} rows)  {rel}"
                )
            continue

        # --- Failure cases ---
        if info["raw_tables"] == 0:
            if not info["has_text"]:
                scanned_images += 1
                label = "SCANNED"  # image-only, no selectable text
            else:
                no_tables += 1
                label = "NO_TABLE"  # text but no table structure
            print(f"  {label}  {rel}  [{info['pages']}p]")
        else:
            wrong_cols += 1
            print(f"  BAD_HDR {rel}  [{info['raw_tables']} table(s)]")
            for i, hdr in enumerate(info["headers_seen"]):
                missing = info["missing_cols"][i]
                norm_str = " | ".join(hdr["normalised"])
                missing_str = ", ".join(sorted(missing)) if missing else "none"
                print(f"          table {i}: [{norm_str}]  missing={missing_str}")
                if args.show_headers or True:
                    raw_str = " | ".join(hdr["raw"])
                    print(f"          raw:   [{raw_str}]")
                # Record unknown raw headers (ones that didn't map to a known column)
                for raw_cell, norm in zip(hdr["raw"], hdr["normalised"]):
                    if (
                        raw_cell.strip()
                        and norm not in _REQUIRED_COLS
                        and norm
                        not in {
                            "club",
                            "race_number",
                            "category_position",
                            "gender_position",
                        }
                    ):
                        unknown_headers[raw_cell.strip()] = (
                            unknown_headers.get(raw_cell.strip(), 0) + 1
                        )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total PDFs audited : {len(pdfs)}")
    print(f"  OK (tables found)  : {ok}")
    print(f"  SCANNED (images)   : {scanned_images}  ← no selectable text, OCR needed")
    print(f"  NO_TABLE           : {no_tables}  ← text but no table structure found")
    print(f"  BAD_HDR            : {wrong_cols}  ← table found but columns don't match")
    print(f"  ERROR              : {errors}")
    print()
    failures = scanned_images + no_tables + wrong_cols + errors
    if failures == 0:
        print("All PDFs parsed successfully!")
    else:
        print(f"  {failures} PDFs could not be parsed.")

    if unknown_headers:
        print()
        print(
            "Unknown raw header cells seen in failing PDFs (candidates for HEADER_MAP):"
        )
        for cell, count in sorted(unknown_headers.items(), key=lambda x: -x[1]):
            print(f"  {count:3d}x  {cell!r}")


if __name__ == "__main__":
    main()
