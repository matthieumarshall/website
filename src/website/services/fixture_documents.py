"""Event licence, risk assessment and medical assessment uploads for fixtures."""

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.models import Fixture, FixtureDocument, FixtureDocumentType, Season
from website.services._common import found
from website.services.compression import compress_document
from website.services.uploads import FileStore, UploadedFile


class FixtureDocuments(BaseModel):
    """A fixture's documents after an upload or delete."""

    model_config = ConfigDict(frozen=True)

    fixture: Fixture
    season: Season | None
    documents: list[FixtureDocument]


class FixtureDocumentService:
    """Stores compact copies of a fixture's compliance documents."""

    def __init__(self, db: Connection, store: FileStore) -> None:
        """Bind the service to a database and the fixture document store."""
        self._db = db
        self._store = store

    def _view(self, fixture: Fixture) -> FixtureDocuments:
        return FixtureDocuments(
            fixture=fixture,
            season=repository.get_season_by_id(self._db, fixture.season_id),
            documents=repository.list_fixture_documents(self._db, fixture.id),
        )

    def _fixture(self, fixture_id: int) -> Fixture:
        return found(
            repository.get_fixture_by_id(self._db, fixture_id), "Fixture not found"
        )

    def list(self, fixture_id: int) -> FixtureDocuments:
        """Return a fixture's documents.

        Raises:
            NotFoundError: If the fixture does not exist.
        """
        return self._view(self._fixture(fixture_id))

    def upload(
        self,
        fixture_id: int,
        doc_type: FixtureDocumentType,
        upload: UploadedFile,
        uploaded_by_id: int | None,
    ) -> FixtureDocuments:
        """Compress and store a document, replacing any of the same type.

        Raises:
            NotFoundError: If the fixture does not exist.
            InvalidRequestError: If the file is not a readable PDF, JPEG or PNG.
            PayloadTooLargeError: If the upload is too large.
        """
        fixture = self._fixture(fixture_id)
        self._store.check(upload)
        packed = compress_document(upload.data)
        previous = repository.get_fixture_document_by_type(
            self._db, fixture_id, doc_type
        )
        filename = self._store.save_bytes(packed.data, packed.suffix)
        repository.upsert_fixture_document(
            self._db,
            fixture_id=fixture_id,
            doc_type=doc_type,
            filename=filename,
            original_name=upload.filename or filename,
            file_type=packed.content_type,
            size_bytes=len(packed.data),
            uploaded_by_id=uploaded_by_id,
        )
        if previous is not None:
            self._store.delete(previous.filename)
        return self._view(fixture)

    def delete(self, fixture_id: int, document_id: int) -> FixtureDocuments:
        """Delete a document record and its file.

        Raises:
            NotFoundError: If the fixture does not exist.
        """
        fixture = self._fixture(fixture_id)
        document = repository.get_fixture_document(self._db, document_id)
        if document is not None and document.fixture_id == fixture_id:
            repository.delete_fixture_document(self._db, document_id)
            self._store.delete(document.filename)
        return self._view(fixture)
