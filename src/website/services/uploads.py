"""Validated storage of user-uploaded files under a data directory."""

import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from website.errors import InvalidRequestError, PayloadTooLargeError

_MB = 1024 * 1024
IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
MAX_IMAGE_BYTES = 5 * _MB
DOCUMENT_EXTENSIONS = (".pdf", ".zip", ".docx", ".xlsx", ".csv", ".txt")
MAX_DOCUMENT_BYTES = 20 * _MB


class UploadedFile(BaseModel):
    """The parts of an HTTP upload that storage needs.

    ``data`` may hold one byte more than the store's limit; that extra byte is
    how an oversized upload is detected without reading it all.
    """

    model_config = ConfigDict(frozen=True)

    filename: str | None
    content_type: str | None
    data: bytes


class UploadPolicy(BaseModel):
    """What a store accepts: content types or file extensions, and a size cap."""

    model_config = ConfigDict(frozen=True)

    max_bytes: int
    content_types: frozenset[str] | None = None
    extensions: tuple[str, ...] | None = None
    default_suffix: str = ""
    too_large_message: str
    bad_type_message: str

    def suffix_for(self, upload: UploadedFile) -> str:
        """Return the stored file suffix, rejecting disallowed uploads.

        Raises:
            InvalidRequestError: If the content type or extension is not allowed.
        """
        if (
            self.content_types is not None
            and upload.content_type not in self.content_types
        ):
            raise InvalidRequestError(self.bad_type_message)
        suffix = Path(upload.filename or "upload").suffix.lower() or self.default_suffix
        if self.extensions is not None and suffix not in self.extensions:
            raise InvalidRequestError(
                f"Unsupported file type '{suffix}'. "
                f"Allowed: {', '.join(self.extensions)}"
            )
        return suffix


IMAGE_POLICY = UploadPolicy(
    max_bytes=MAX_IMAGE_BYTES,
    content_types=IMAGE_CONTENT_TYPES,
    default_suffix=".jpg",
    too_large_message="Image exceeds 5 MB limit",
    bad_type_message="Unsupported image type",
)
DOCUMENT_POLICY = UploadPolicy(
    max_bytes=MAX_DOCUMENT_BYTES,
    extensions=DOCUMENT_EXTENSIONS,
    too_large_message="File exceeds 20 MB limit",
    bad_type_message="Unsupported file type",
)


class FileStore:
    """Saves uploads under a directory with random, unguessable names."""

    def __init__(self, directory: Path, policy: UploadPolicy) -> None:
        """Store files in *directory*, accepting only what *policy* allows."""
        self.directory = directory
        self.policy = policy

    def check(self, upload: UploadedFile) -> str:
        """Validate an upload and return the suffix it will be stored with.

        Raises:
            InvalidRequestError: If the type is not allowed.
            PayloadTooLargeError: If the file is too large.
        """
        suffix = self.policy.suffix_for(upload)
        if len(upload.data) > self.policy.max_bytes:
            raise PayloadTooLargeError(self.policy.too_large_message)
        return suffix

    def save(self, upload: UploadedFile, subdirectory: str = "") -> str:
        """Validate and write an upload, returning its stored filename.

        Raises:
            InvalidRequestError: If the type is not allowed.
            PayloadTooLargeError: If the file is too large.
        """
        filename = f"{uuid.uuid4().hex}{self.check(upload)}"
        target_dir = self.directory / subdirectory
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_bytes(upload.data)
        return filename

    def delete(self, filename: str, subdirectory: str = "") -> None:
        """Remove a stored file if it exists."""
        (self.directory / subdirectory / filename).unlink(missing_ok=True)
