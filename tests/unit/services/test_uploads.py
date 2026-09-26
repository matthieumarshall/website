"""FileStore: upload validation and storage."""

from pathlib import Path

import pytest

from website.errors import InvalidRequestError, PayloadTooLargeError
from website.services.uploads import (
    DOCUMENT_POLICY,
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
