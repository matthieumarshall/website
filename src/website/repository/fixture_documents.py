"""Fixture licence and assessment document persistence."""

from website.db import Connection
from website.models import FixtureDocument, FixtureDocumentType
from website.repository._rows import fetch_all, fetch_one, require

_SELECT = (
    "SELECT id, fixture_id, doc_type, filename, original_name, file_type,"
    " size_bytes, uploaded_at, uploaded_by_id FROM fixture_documents"
)


def list_fixture_documents(db: Connection, fixture_id: int) -> list[FixtureDocument]:
    """Return a fixture's documents ordered by type."""
    return fetch_all(
        db,
        FixtureDocument,
        f"{_SELECT} WHERE fixture_id = ? ORDER BY doc_type",
        [fixture_id],
    )


def get_fixture_document(db: Connection, document_id: int) -> FixtureDocument | None:
    """Return the document with *document_id*, or None."""
    return fetch_one(db, FixtureDocument, f"{_SELECT} WHERE id = ?", [document_id])


def get_fixture_document_by_type(
    db: Connection, fixture_id: int, doc_type: FixtureDocumentType
) -> FixtureDocument | None:
    """Return a fixture's document of *doc_type*, or None."""
    return fetch_one(
        db,
        FixtureDocument,
        f"{_SELECT} WHERE fixture_id = ? AND doc_type = ?",
        [fixture_id, doc_type.value],
    )


def upsert_fixture_document(
    db: Connection,
    fixture_id: int,
    doc_type: FixtureDocumentType,
    filename: str,
    original_name: str,
    file_type: str,
    size_bytes: int,
    uploaded_by_id: int | None,
) -> FixtureDocument:
    """Store a fixture's document, replacing any of the same type."""
    db.execute(
        "DELETE FROM fixture_documents WHERE fixture_id = ? AND doc_type = ?",
        [fixture_id, doc_type.value],
    )
    db.execute(
        "INSERT INTO fixture_documents (fixture_id, doc_type, filename,"
        " original_name, file_type, size_bytes, uploaded_by_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            fixture_id,
            doc_type.value,
            filename,
            original_name,
            file_type,
            size_bytes,
            uploaded_by_id,
        ],
    )
    return require(
        get_fixture_document_by_type(db, fixture_id, doc_type), "fixture document"
    )


def delete_fixture_document(db: Connection, document_id: int) -> str | None:
    """Delete a document record, returning its filename (None if absent)."""
    document = get_fixture_document(db, document_id)
    if document is None:
        return None
    db.execute("DELETE FROM fixture_documents WHERE id = ?", [document_id])
    return document.filename
