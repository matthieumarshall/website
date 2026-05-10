"""Fast audit of all results PDFs - outputs CSV summary and extracts text for failing PDFs.

Usage:
    uv run python scripts/fast_audit.py               # full audit + save text files
    uv run python scripts/fast_audit.py --no-save     # just print summary counts
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber required. Run: uv add pdfplumber")

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))
import _migration_helpers as mh  # noqa: E402

_RESULTS_ROOT = (
    Path(__file__).parent.parent / "data" / "original_website" / "files" / "results"
)
_PDF_RE = re.compile(r"^(\d{8})-Rnd(\d+)-(.+?)-min\.pdf$", re.IGNORECASE)
_REQUIRED_COLS = {"position", "athlete_name", "time", "category", "gender"}
_OUT_DIR = Path(__file__).parent.parent / "data" / "pdf_text_dump"

# Keywords that indicate a structured result table header is present in the text
_HEADER_KEYWORDS = re.compile(
    r"\b(pos|position|place|name|athlete|time|category|cat|gender|club|race\s*no)\b",
    re.IGNORECASE,
)
# Minimum header keyword hits to suspect a real table header row exists
_HEADER_KW_THRESHOLD = 3


def _quick_text_classify(text: str) -> str | None:
    """Try to classify from text alone. Returns 'OK_MAYBE', 'SCANNED', or None (inconclusive)."""
    if not text or not text.strip():
        return "SCANNED"  # no text at all → likely a scanned image

    # Count header-like keyword hits per line
    lines = text.splitlines()
    for line in lines[:30]:  # check first 30 lines for a header row
        hits = len(_HEADER_KEYWORDS.findall(line))
        if hits >= _HEADER_KW_THRESHOLD:
            return "OK_MAYBE"  # has a probable header row, worth doing table extraction
    return None  # inconclusive — still needs table check


def _classify_pdf(pdf_path: Path) -> tuple[str, list[str], str]:
    """Return (status, first_raw_header, extracted_text_sample).

    Strategy:
    1. Extract text from page 1 only (fast — no table detection).
    2. If no text → SCANNED (image-only PDF).
    3. If text has table-like keyword density → run table extraction on all pages.
    4. Otherwise → text present but no table → NO_TABLE.

    Status values:
      OK        - has recognised result tables
      BAD_HDR   - has tables but no required cols
      SCANNED   - no selectable text (image scan)
      NO_TABLE  - has text, no table structure found
      ERROR     - exception
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Step 1: fast text extraction from first page only
            first_text = ""
            for page in pdf.pages[:2]:
                t = page.extract_text() or ""
                if t.strip():
                    first_text += t
                    break

            quick = _quick_text_classify(first_text)
            text_sample = first_text[:800]

            if quick == "SCANNED":
                return "SCANNED", [], text_sample

            # Step 2: only do expensive table extraction if text looks table-like
            if quick is None:
                # Text present but doesn't look like a result table header
                return "NO_TABLE", [], text_sample

            # quick == 'OK_MAYBE' — run full table extraction
            recognised = 0
            first_raw_header: list[str] = []
            all_tables = 0

            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or not table[0]:
                        continue
                    all_tables += 1
                    raw = table[0]
                    normalised = [mh.normalise_header(c or "") for c in raw]
                    missing = _REQUIRED_COLS - set(normalised)
                    if not missing:
                        recognised += 1
                    if not first_raw_header:
                        first_raw_header = [c or "" for c in raw]

            if recognised > 0:
                return "OK", first_raw_header, text_sample
            if all_tables > 0:
                return "BAD_HDR", first_raw_header, text_sample
            return "NO_TABLE", [], text_sample
    except Exception as exc:  # noqa: BLE001
        return "ERROR", [], str(exc)
    except Exception as exc:  # noqa: BLE001
        return "ERROR", [], str(exc)


def _all_pdfs() -> list[Path]:
    pdfs = sorted(_RESULTS_ROOT.rglob("*-min.pdf"))
    return [p for p in pdfs if _PDF_RE.match(p.name)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-save", action="store_true", help="Skip saving text dumps")
    args = parser.parse_args()

    pdfs = _all_pdfs()
    print(f"Found {len(pdfs)} PDFs to audit...", flush=True)

    counts: dict[str, int] = {
        "OK": 0,
        "BAD_HDR": 0,
        "SCANNED": 0,
        "NO_TABLE": 0,
        "ERROR": 0,
    }
    rows: list[dict] = []

    if not args.no_save:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)

    for i, pdf_path in enumerate(pdfs, 1):
        rel = str(pdf_path.relative_to(_RESULTS_ROOT))
        status, hdr, text_sample = _classify_pdf(pdf_path)
        counts[status] = counts.get(status, 0) + 1
        rows.append({"status": status, "path": rel, "header": " | ".join(hdr)})
        symbol = {
            "OK": "✓",
            "BAD_HDR": "H",
            "SCANNED": "S",
            "NO_TABLE": "T",
            "ERROR": "E",
        }.get(status, "?")
        print(f"[{i:3d}/{len(pdfs)}] {symbol} {status:8s}  {rel}", flush=True)

        # Save text dump for non-OK files so we can inspect them
        if not args.no_save and status != "OK" and text_sample:
            safe_name = rel.replace("\\", "_").replace("/", "_").replace(".pdf", ".txt")
            out_file = _OUT_DIR / safe_name
            out_file.write_text(text_sample, encoding="utf-8", errors="replace")

    # Write CSV
    csv_path = Path(__file__).parent.parent / "data" / "pdf_audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["status", "path", "header"])
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total PDFs     : {len(pdfs)}")
    for k, v in sorted(counts.items()):
        print(f"  {k:8s}       : {v}")
    print()
    print(f"  CSV saved to   : {csv_path}")
    if not args.no_save:
        print(f"  Text dumps in  : {_OUT_DIR}")

    # Show BAD_HDR headers (fixable ones with different column names)
    bad_hdr_pdfs = [r for r in rows if r["status"] == "BAD_HDR"]
    if bad_hdr_pdfs:
        print()
        print("BAD_HDR files (may be fixable with HEADER_MAP extension):")
        for r in bad_hdr_pdfs[:20]:
            print(f"  {r['path']}")
            if r["header"]:
                print(f"    headers: {r['header']}")


if __name__ == "__main__":
    main()
