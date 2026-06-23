"""Batch import race results from a folder tree of CSV files.

Expected root directory structure:
    <root>/r1/*.csv
    <root>/r2/*.csv
    ...

Each CSV file should contain a header row with these columns:
    position, athlete_name, time, category, gender

Example:
    uv run python scripts/seed_results_batch.py "2025-2026" \
        C:/Users/MatthieuMarshall/Documents/Admin/personal/course_a_pied/pyresults/input_data

The script maps the round folders to fixture titles:
    r1 -> Round 1
    r2 -> Round 2
    round 1 -> Round 1

It imports every CSV file in each round folder as a separate race.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project source is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cli.seed_results import import_results


def _normalize_fixture_title(folder_name: str) -> str:
    text = folder_name.strip().lower().replace("_", " ")
    if text.startswith("round"):
        suffix = text[len("round") :].strip()
        if suffix.isdigit():
            return f"Round {int(suffix)}"
    if text.startswith("r") and text[1:].isdigit():
        return f"Round {int(text[1:])}"
    return folder_name.strip()


def _normalize_race_name(file_stem: str) -> str:
    cleaned = file_stem.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return file_stem
    return " ".join(
        part.capitalize() if part.islower() else part for part in cleaned.split()
    )


def _collect_csv_paths(root_dir: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for folder in sorted(root_dir.iterdir()):
        if not folder.is_dir():
            continue
        fixture_title = _normalize_fixture_title(folder.name)
        for csv_path in sorted(folder.glob("*.csv")):
            entries.append((fixture_title, csv_path))
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch import race results from round CSV folders."
    )
    parser.add_argument("season_name", help='Season name, e.g. "2025-2026"')
    parser.add_argument(
        "root_dir",
        type=Path,
        help="Root directory containing round folders, e.g. r1, r2, r3",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned imports without writing to the database.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue importing other files if one file fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.root_dir.exists() or not args.root_dir.is_dir():
        raise SystemExit(f"Root directory not found: {args.root_dir}")

    entries = _collect_csv_paths(args.root_dir)
    if not entries:
        raise SystemExit(f"No CSV files found in {args.root_dir}")

    print(f"Found {len(entries)} CSV files in {args.root_dir}")
    for fixture_title, csv_path in entries:
        race_name = _normalize_race_name(csv_path.stem)
        print(f"\nFixture: {fixture_title}")
        print(f"  CSV: {csv_path}")
        print(f"  Race: {race_name}")
        if args.dry_run:
            continue
        try:
            import_results(args.season_name, fixture_title, race_name, csv_path)
        except SystemExit as exc:
            if exc.code != 0:
                print(f"Error importing {csv_path}: {exc}")
                if not args.continue_on_error:
                    raise
        except Exception as exc:
            print(f"Error importing {csv_path}: {exc}")
            if not args.continue_on_error:
                raise SystemExit(1)
    print("\nBatch import complete.")


if __name__ == "__main__":
    main()
