"""Keep stored documents gzipped on disk, transparently to their callers.

A document whose logical path is ``name.pdf`` is written as ``name.pdf.gz``
when gzip makes it smaller, and as ``name.pdf`` otherwise. Database rows and
URLs always use the logical name; readers resolve it with :func:`stored_file`.
"""

import gzip
from collections.abc import Callable
from pathlib import Path

ARCHIVE_SUFFIX = ".gz"
_GZIP_LEVEL = 9


def archived_path(path: Path) -> Path:
    """Return where the gzipped copy of *path* lives."""
    return path.with_name(path.name + ARCHIVE_SUFFIX)


def is_archived(path: Path | str) -> bool:
    """Return whether *path* names a gzipped archive."""
    return str(path).endswith(ARCHIVE_SUFFIX)


def pack(data: bytes) -> bytes | None:
    """Return *data* gzipped, or None if gzip would not make it smaller."""
    # mtime=0 keeps the output deterministic for identical input.
    packed = gzip.compress(data, compresslevel=_GZIP_LEVEL, mtime=0)
    return packed if len(packed) < len(data) else None


def write_archived(path: Path, data: bytes) -> Path:
    """Store *data* under logical *path*, gzipped if smaller; return the file written.

    The file is written to a temporary name and moved into place, and only then
    is the other form removed, so an interrupted write never loses a copy.
    """
    packed = pack(data)
    archive = archived_path(path)
    target, stale = (archive, path) if packed is not None else (path, archive)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(packed if packed is not None else data)
    temporary.replace(target)
    stale.unlink(missing_ok=True)
    return target


def archive_file(path: Path, shrink: Callable[[bytes], bytes] | None = None) -> Path:
    """Re-store the file at logical *path*, optionally shrinking it first.

    Idempotent: an already-archived file is decompressed, re-shrunk and
    re-packed, which leaves it as small as before.

    Raises:
        FileNotFoundError: If neither *path* nor its archive exists.
    """
    data = read_stored(path)
    return write_archived(path, shrink(data) if shrink is not None else data)


def stored_file(path: Path) -> Path | None:
    """Return the file holding logical *path* — itself or its archive — or None."""
    if path.is_file():
        return path
    archive = archived_path(path)
    return archive if archive.is_file() else None


def read_stored(path: Path) -> bytes:
    """Return the original bytes of the file at *path*, un-gzipping an archive.

    Raises:
        FileNotFoundError: If neither *path* nor its archive exists.
    """
    found = stored_file(path)
    if found is None:
        raise FileNotFoundError(path)
    data = found.read_bytes()
    return gzip.decompress(data) if is_archived(found) else data


def remove_stored(path: Path) -> None:
    """Delete logical *path* and its archive, if either exists."""
    path.unlink(missing_ok=True)
    archived_path(path).unlink(missing_ok=True)
