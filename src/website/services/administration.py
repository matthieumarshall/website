"""Administration document sections and uploads."""

import logging
import re

from website import repository
from website.db import Connection
from website.errors import InvalidRequestError
from website.models import AdministrationSection
from website.models.forms import AdministrationSectionForm
from website.services._common import found
from website.services.uploads import FileStore, UploadedFile

_logger = logging.getLogger(__name__)
_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


class AdministrationService:
    """Manage document sections and the files stored in them."""

    def __init__(self, db: Connection, document_store: FileStore) -> None:
        """Bind the service to a database and the document file store."""
        self._db = db
        self._documents = document_store

    def sections(self) -> list[AdministrationSection]:
        """Return every section with its documents."""
        return repository.list_administration_sections(self._db)

    def create_section(self, form: AdministrationSectionForm) -> None:
        """Add a section at the end of the list.

        Raises:
            InvalidRequestError: If the slug or title is invalid, or the slug
                is already used.
        """
        slug = form.slug.strip().lower()
        if not _SLUG_PATTERN.match(slug):
            raise InvalidRequestError(
                "Slug must contain only lowercase letters, digits, and hyphens."
            )
        title = form.title.strip()
        if not title:
            raise InvalidRequestError("Title is required.")
        try:
            repository.create_administration_section(
                self._db,
                slug=slug,
                title=title,
                description=form.description.strip(),
                sort_order=len(self.sections()),
            )
        except repository.IntegrityError as exc:
            _logger.exception("Failed to create administration section (slug=%s)", slug)
            raise InvalidRequestError(
                "A section with that slug already exists."
            ) from exc

    def delete_section(self, section_id: int) -> None:
        """Delete an empty section.

        Raises:
            InvalidRequestError: If the section still has documents.
        """
        try:
            repository.delete_administration_section(self._db, section_id)
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc

    def upload_document(
        self,
        section_id: int,
        display_name: str,
        upload: UploadedFile,
        uploaded_by_id: int | None,
    ) -> None:
        """Store a document in a section, listed first.

        Raises:
            NotFoundError: If the section does not exist.
            InvalidRequestError: If the name is blank or the file type is not allowed.
            PayloadTooLargeError: If the file is too large.
        """
        section = found(
            repository.get_administration_section(self._db, section_id),
            "Section not found",
        )
        suffix = self._documents.check(upload)
        name = display_name.strip()
        if not name:
            raise InvalidRequestError("Display name is required.")
        filename = self._documents.save(upload, subdirectory=section.slug)
        repository.create_administration_document(
            self._db,
            section_id=section_id,
            display_name=name,
            filename=filename,
            file_type=suffix.lstrip(".").upper(),
            sort_order=len(section.documents),
            uploaded_by_id=uploaded_by_id,
        )

    def delete_document(self, doc_id: int) -> None:
        """Delete a document record and its file (if any)."""
        deleted = repository.delete_administration_document(self._db, doc_id)
        if deleted is not None:
            self._documents.delete(deleted.filename, subdirectory=deleted.section_slug)
