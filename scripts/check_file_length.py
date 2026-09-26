"""Fail when a Python module grows beyond the agreed size limit.

Ruff has no "max module lines" rule, so this small check runs in pre-commit
and CI.  Modules above the warning threshold are reported but do not fail.

Usage:
    python scripts/check_file_length.py [--max 1000] [--warn 500] [PATH ...]
"""

import argparse
import sys
from pathlib import Path


def _python_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py":
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["src"])
    parser.add_argument("--max", type=int, default=1000, dest="max_lines")
    parser.add_argument("--warn", type=int, default=500, dest="warn_lines")
    args = parser.parse_args(argv)

    failed = False
    for path in _python_files(args.paths):
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > args.max_lines:
            print(f"ERROR {path}: {count} lines (limit {args.max_lines})")
            failed = True
        elif count > args.warn_lines:
            print(
                f"warning {path}: {count} lines (consider splitting above {args.warn_lines})"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
