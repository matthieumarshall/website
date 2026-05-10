"""One-shot script: backfill fixtures.source_pdf for all existing fixtures.

Scans the original_website results directory, matches each PDF filename to a
fixture in the database by date, and sets source_pdf to the path relative to
data/original_website/files/results/.

Run with:
    uv run python scripts/_backfill_source_pdf.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "src"))

import _migration_helpers as mh  # noqa: E402
from website import repository  # noqa: E402

_RESULTS_ROOT = _ROOT / "data" / "original_website" / "files" / "results"
_PDF_RE = re.compile(r"^(\d{8})-Rnd(\d+)-(.+)-min\.pdf$", re.IGNORECASE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill fixtures.source_pdf")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()

    con = mh.open_db()

    updated = 0
    skipped = 0
    not_found = 0

    for pdf_path in sorted(_RESULTS_ROOT.rglob("*.pdf")):
        m = _PDF_RE.match(pdf_path.name)
        if not m:
            continue

        date_str = m.group(1)
        fixture_date = datetime.strptime(date_str, "%Y%m%d").date()

        # Find the season id from the directory name (e.g. "2021-2022")
        season_name = pdf_path.parent.name  # e.g. "2021-2022"
        season_row = con.execute(
            "SELECT id FROM seasons WHERE lower(name) = lower(?)", [season_name]
        ).fetchone()
        if season_row is None:
            skipped += 1
            continue

        season_id = int(season_row[0])
        fixture_id = mh.find_fixture_by_date(con, fixture_date, season_id)
        if fixture_id is None:
            not_found += 1
            print(
                f"  No fixture for {pdf_path.name} ({fixture_date}) in {season_name!r}"
            )
            continue

        source_rel = str(pdf_path.relative_to(_RESULTS_ROOT)).replace("\\", "/")
        if args.dry_run:
            print(f"  DRY: fixture {fixture_id} <- {source_rel}")
        else:
            repository.set_fixture_source_pdf(con, fixture_id, source_rel)
        updated += 1

    if not args.dry_run:
        con.commit()

    print(
        f"\nDone. Updated: {updated}  |  skipped (no season): {skipped}"
        f"  |  not found (no fixture): {not_found}"
    )


if __name__ == "__main__":
    main()
