"""Move existing results PDFs from data/original_website to data/uploads/results/{fixture_id}/.

This backfill script updates the database with new relative paths after moving PDFs.
Run this once after pulling the latest migrate_results.py changes.

Usage
-----
    uv run python scripts/_backfill_move_pdfs.py [--dry-run]

Options
-------
--dry-run   Show what would be moved without actually moving files or updating the DB.
"""

import argparse
import sys
from pathlib import Path

import duckdb

_ROOT = Path(__file__).parent.parent
_ORIGINAL_RESULTS_ROOT = _ROOT / "data" / "original_website" / "files" / "results"
_UPLOADS_DIR = _ROOT / "data" / "uploads"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be moved without doing it",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(_ROOT / "src"))
    from website.database import _get_db_path
    from website import repository

    db_path = _get_db_path()
    con = duckdb.connect(str(db_path))

    # Get all fixtures with a source_pdf set (old paths from original_website)
    rows = con.execute(
        "SELECT id, source_pdf FROM fixtures WHERE source_pdf IS NOT NULL"
    ).fetchall()

    moved_count = 0
    not_found_count = 0

    for fixture_id, old_rel_path in rows:
        # Skip if it's already using the new format (starts with "results/")
        if old_rel_path.startswith("results/"):
            continue

        old_full_path = _ORIGINAL_RESULTS_ROOT / old_rel_path
        if not old_full_path.exists():
            print(f"  NOT FOUND: fixture_id={fixture_id}, expected at {old_full_path}")
            not_found_count += 1
            continue

        # New destination: data/uploads/results/{fixture_id}/{filename}
        filename = old_full_path.name
        dest_dir = _UPLOADS_DIR / "results" / str(fixture_id)
        dest_path = dest_dir / filename
        new_rel_path = str(dest_path.relative_to(_UPLOADS_DIR)).replace("\\", "/")

        if args.dry_run:
            print(
                f"  Would move fixture_id={fixture_id}: {old_rel_path} -> {new_rel_path}"
            )
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(old_full_path.read_bytes())
            repository.set_fixture_source_pdf(con, fixture_id, new_rel_path)
            print(f"  Moved fixture_id={fixture_id}: {old_rel_path} -> {new_rel_path}")
            moved_count += 1

    con.close()

    if args.dry_run:
        print(f"\nDry-run: Would have moved {len(rows) - not_found_count} PDFs")
    else:
        print(f"\nDone. Moved: {moved_count} | Not found: {not_found_count}")


if __name__ == "__main__":
    main()
