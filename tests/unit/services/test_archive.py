"""Unit tests: gzipped storage of documents at rest."""

import gzip
from pathlib import Path

import pytest

from website.services.archive import (
    archive_file,
    archived_path,
    pack,
    read_stored,
    remove_stored,
    stored_file,
    write_archived,
)

_COMPRESSIBLE = b"Position,Name,Club,Time\n" + b"1,A Runner,Oxford AC,30:00\n" * 500


def test_pack_returns_none_when_gzip_does_not_help() -> None:
    assert pack(b"x") is None
    packed = pack(_COMPRESSIBLE)
    assert packed is not None
    assert gzip.decompress(packed) == _COMPRESSIBLE


def test_pack_is_deterministic() -> None:
    assert pack(_COMPRESSIBLE) == pack(_COMPRESSIBLE)


def test_compressible_data_is_stored_gzipped(tmp_path: Path) -> None:
    logical = tmp_path / "results.csv"
    written = write_archived(logical, _COMPRESSIBLE)
    assert written == archived_path(logical)
    assert not logical.exists()
    assert stored_file(logical) == written
    assert read_stored(logical) == _COMPRESSIBLE
    assert [p.name for p in tmp_path.iterdir()] == ["results.csv.gz"]


def test_incompressible_data_is_stored_plain(tmp_path: Path) -> None:
    logical = tmp_path / "tiny.pdf"
    assert write_archived(logical, b"x") == logical
    assert stored_file(logical) == logical
    assert read_stored(logical) == b"x"


def test_rewrite_removes_the_other_form(tmp_path: Path) -> None:
    logical = tmp_path / "doc.txt"
    write_archived(logical, _COMPRESSIBLE)
    write_archived(logical, b"x")
    assert [p.name for p in tmp_path.iterdir()] == ["doc.txt"]


def test_missing_file(tmp_path: Path) -> None:
    logical = tmp_path / "gone.pdf"
    assert stored_file(logical) is None
    with pytest.raises(FileNotFoundError):
        read_stored(logical)
    remove_stored(logical)


def test_remove_stored_deletes_both_forms(tmp_path: Path) -> None:
    logical = tmp_path / "doc.pdf"
    logical.write_bytes(b"plain")
    archived_path(logical).write_bytes(b"packed")
    remove_stored(logical)
    assert list(tmp_path.iterdir()) == []


def test_archive_file_shrinks_and_is_idempotent(tmp_path: Path) -> None:
    logical = tmp_path / "doc.txt"
    logical.write_bytes(_COMPRESSIBLE + b"padding")
    first = archive_file(logical, lambda data: data.removesuffix(b"padding"))
    size = first.stat().st_size
    second = archive_file(logical)
    assert second == first
    assert second.stat().st_size == size
    assert read_stored(logical) == _COMPRESSIBLE
