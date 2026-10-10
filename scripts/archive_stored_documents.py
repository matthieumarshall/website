"""Shrink and gzip every stored document already on disk.

New uploads are shrunk and archived as they are saved (see
``website.services.archive``). This one-off migration applies the same
treatment to files stored before that change:

- PDFs are rewritten losslessly with compressed streams (pikepdf), and
  ``.zip`` / ``.docx`` / ``.xlsx`` containers are re-deflated;
- the result is gzipped to ``<name>.gz`` when that is smaller, and the
  original file is removed.

Database rows are not touched: they keep the logical file name, and the app
serves ``<name>.gz`` in its place with ``Content-Encoding: gzip``.

The script is idempotent and safe to re-run (for example after importing more
legacy documents). Each file is verified before its original is removed.

Usage
-----
    uv run python scripts/archive_stored_documents.py --dry-run
    uv run python scripts/archive_stored_documents.py

Options
-------
--dry-run   Report the savings without changing any file.
--root DIR  Directory to process (repeatable). Defaults to the app's document
            stores: data/uploads (administration documents and results PDFs)
            and data/fixture-docs.
"""

import argparse
import gzip
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from website.config import Settings  # noqa: E402
from website.services.archive import (  # noqa: E402
    ARCHIVE_SUFFIX,
    pack,
    read_stored,
    stored_file,
    write_archived,
)
from website.services.compression import shrink_document  # noqa: E402
from website.services.uploads import (  # noqa: E402
    DOCUMENT_EXTENSIONS,
    FIXTURE_DOC_EXTENSIONS,
)

# Images (news uploads, fixture-doc photos) are already JPEG/PNG compressed;
# only document formats are archived.
_ARCHIVABLE = frozenset(DOCUMENT_EXTENSIONS) | (
    frozenset(FIXTURE_DOC_EXTENSIONS) - {".jpg", ".jpeg", ".png"}
)


def _default_roots() -> list[Path]:
    settings = Settings()
    return [_ROOT / settings.uploads_dir, _ROOT / settings.fixture_docs_dir]


def _logical_documents(root: Path) -> list[Path]:
    """Return the logical path of each archivable document under *root*."""
    logical: set[Path] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.name.endswith(".tmp"):
            continue
        name = path.with_name(path.name.removesuffix(ARCHIVE_SUFFIX))
        if name.suffix.lower() in _ARCHIVABLE:
            logical.add(name)
    return sorted(logical)


def _process(path: Path, dry_run: bool) -> tuple[int, int, bool]:
    """Shrink and archive one document.

    Returns its size on disk before and after, and whether it ends up gzipped.
    """
    current = stored_file(path)
    assert current is not None
    before = current.stat().st_size
    original = read_stored(path)
    shrunk = shrink_document(original, path.suffix)
    if dry_run:
        packed = pack(shrunk)
        if packed is None:
            return before, len(shrunk), False
        return before, len(packed), True
    written = write_archived(path, shrunk)
    stored = written.read_bytes()
    restored = gzip.decompress(stored) if written != path else stored
    if restored != shrunk:
        raise RuntimeError(f"verification failed for {written}")
    return before, len(stored), written != path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report without changing files"
    )
    parser.add_argument(
        "--root", type=Path, action="append", help="Directory to process"
    )
    args = parser.parse_args()

    roots = args.root or _default_roots()
    total_before = total_after = processed = failed = 0
    for root in roots:
        if not root.is_dir():
            print(f"[SKIP] {root} does not exist")
            continue
        print(f"=== {root} ===")
        for path in _logical_documents(root):
            try:
                before, after, gzipped = _process(path, args.dry_run)
            except Exception as exc:
                failed += 1
                print(f"  [FAIL] {path}: {exc}")
                continue
            processed += 1
            total_before += before
            total_after += after
            form = "gz" if gzipped else "raw"
            print(f"  [OK] {path.relative_to(root)}  {before:,} -> {after:,} ({form})")

    saved = total_before - total_after
    share = saved / total_before if total_before else 0
    verb = "Would save" if args.dry_run else "Saved"
    print(
        f"\n{processed} documents, {failed} failed. "
        f"{total_before / 1e6:.1f} MB -> {total_after / 1e6:.1f} MB. "
        f"{verb} {saved / 1e6:.1f} MB ({share:.0%})."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
