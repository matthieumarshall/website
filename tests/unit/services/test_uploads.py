"""FileStore: upload validation and storage."""

import gzip
from pathlib import Path

import pytest

from website.errors import InvalidRequestError, PayloadTooLargeError
from website.services.uploads import (
    DOCUMENT_POLICY,
    FIXTURE_DOC_POLICY,
    IMAGE_POLICY,
    MAX_IMAGE_BYTES,
    FileStore,
    UploadedFile,
)


def _upload(
    filename: str | None, content_type: str | None, data: bytes = b"x"
) -> UploadedFile:
    return UploadedFile(filename=filename, content_type=content_type, data=data)


class TestImageStore:
    def test_saves_with_random_name_and_default_suffix(self, tmp_path: Path) -> None:
        store = FileStore(tmp_path, IMAGE_POLICY)
        name = store.save(_upload(None, "image/png", b"png-bytes"))
        assert name.endswith(".jpg")
        assert (tmp_path / name).read_bytes() == b"png-bytes"
        store.delete(name)
        assert not (tmp_path / name).exists()

    def test_rejects_non_images(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidRequestError, match="Unsupported image type"):
            FileStore(tmp_path, IMAGE_POLICY).save(_upload("a.txt", "text/plain"))

    def test_rejects_oversized_images(self, tmp_path: Path) -> None:
        big = _upload("a.png", "image/png", b"x" * (MAX_IMAGE_BYTES + 1))
        with pytest.raises(PayloadTooLargeError):
            FileStore(tmp_path, IMAGE_POLICY).save(big)
        assert list(tmp_path.iterdir()) == []


class TestDocumentStore:
    def test_saves_into_subdirectory_keeping_extension(self, tmp_path: Path) -> None:
        store = FileStore(tmp_path, DOCUMENT_POLICY)
        name = store.save(_upload("Minutes.PDF", "application/pdf"), "agendas")
        assert name.endswith(".pdf")
        assert (tmp_path / "agendas" / name).is_file()

    def test_rejects_disallowed_extension(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidRequestError, match="Unsupported file type '.exe'"):
            FileStore(tmp_path, DOCUMENT_POLICY).check(_upload("run.exe", None))

    def test_delete_missing_file_is_harmless(self, tmp_path: Path) -> None:
        FileStore(tmp_path, DOCUMENT_POLICY).delete("nope.pdf", "none")


class TestArchivingStore:
    _TEXT = b"1,A Runner,Oxford AC,30:00\n" * 500

    def test_document_policies_archive_and_image_policy_does_not(self) -> None:
        assert DOCUMENT_POLICY.archive
        assert FIXTURE_DOC_POLICY.archive
        assert not IMAGE_POLICY.archive

    def test_compressible_upload_is_stored_gzipped(self, tmp_path: Path) -> None:
        store = FileStore(tmp_path, DOCUMENT_POLICY)
        name = store.save(_upload("results.csv", "text/csv", self._TEXT), "agendas")
        assert name.endswith(".csv")
        assert not (tmp_path / "agendas" / name).exists()
        archive = tmp_path / "agendas" / f"{name}.gz"
        assert gzip.decompress(archive.read_bytes()) == self._TEXT

    def test_images_are_never_gzipped(self, tmp_path: Path) -> None:
        name = FileStore(tmp_path, IMAGE_POLICY).save_bytes(self._TEXT, ".png")
        assert (tmp_path / name).read_bytes() == self._TEXT

    def test_copy_and_delete_follow_the_archive(self, tmp_path: Path) -> None:
        store = FileStore(tmp_path, DOCUMENT_POLICY)
        name = store.save_bytes(self._TEXT, ".txt")
        duplicate = store.copy(name)
        assert duplicate != name
        assert (tmp_path / f"{duplicate}.gz").read_bytes() == (
            tmp_path / f"{name}.gz"
        ).read_bytes()
        store.delete(name)
        store.delete(duplicate)
        assert list(tmp_path.iterdir()) == []

    def test_copy_of_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            FileStore(tmp_path, DOCUMENT_POLICY).copy("nope.pdf")
