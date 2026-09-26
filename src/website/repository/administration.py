"""Administration section and document persistence."""

from pydantic import BaseModel, ConfigDict

from website.db import Connection
from website.models import (
    AdministrationDocument,
    AdministrationSection,
    DeletedDocument,
)
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

_SECTION_SELECT = (
    "SELECT id, slug, title, description, sort_order FROM administration_sections"
)
_DOCUMENT_SELECT = (
    "SELECT d.id, d.section_id, d.display_name, d.filename, d.file_type,"
    " d.sort_order, s.slug AS section_slug"
    " FROM administration_documents d"
    " JOIN administration_sections s ON s.id = d.section_id"
)


class _SectionRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    title: str
    description: str
    sort_order: int


class _DocumentRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    section_id: int
    display_name: str
    filename: str
    file_type: str
    sort_order: int
    section_slug: str

    def to_document(self) -> AdministrationDocument:
        return AdministrationDocument(
            id=self.id,
            section_id=self.section_id,
            display_name=self.display_name,
            filename=self.filename,
            href=f"/uploads/administration/{self.section_slug}/{self.filename}",
            file_type=self.file_type,
            sort_order=self.sort_order,
        )


def _documents_for(db: Connection, section_id: int) -> list[AdministrationDocument]:
    rows = fetch_all(
        db,
        _DocumentRow,
        f"{_DOCUMENT_SELECT} WHERE d.section_id = ?"  # noqa: S608
        " ORDER BY d.sort_order DESC, d.display_name ASC",
        [section_id],
    )
    return [row.to_document() for row in rows]


def _with_documents(db: Connection, row: _SectionRow) -> AdministrationSection:
    return AdministrationSection(
        **row.model_dump(), documents=_documents_for(db, row.id)
    )


def list_administration_sections(db: Connection) -> list[AdministrationSection]:
    """Return every section with its documents, in display order."""
    rows = fetch_all(
        db,
        _SectionRow,
        f"{_SECTION_SELECT} ORDER BY sort_order ASC, title ASC",  # noqa: S608
    )
    return [_with_documents(db, row) for row in rows]


def get_administration_section(
    db: Connection, section_id: int
) -> AdministrationSection | None:
    """Return a section with its documents, or None."""
    row = fetch_one(db, _SectionRow, f"{_SECTION_SELECT} WHERE id = ?", [section_id])  # noqa: S608
    return _with_documents(db, row) if row else None


def create_administration_section(
    db: Connection, slug: str, title: str, description: str, sort_order: int = 0
) -> AdministrationSection:
    """Insert an (empty) section and return it."""
    db.execute(
        "INSERT INTO administration_sections (slug, title, description, sort_order)"
        " VALUES (?, ?, ?, ?)",
        [slug, title, description, sort_order],
    )
    row = fetch_one(db, _SectionRow, f"{_SECTION_SELECT} WHERE slug = ?", [slug])  # noqa: S608
    return AdministrationSection(
        **require(row, "administration section").model_dump(), documents=[]
    )


def delete_administration_section(db: Connection, section_id: int) -> None:
    """Delete an empty section.

    Raises:
        ValueError: If the section still contains documents.
    """
    count = fetch_count(
        db,
        "SELECT COUNT(*) FROM administration_documents WHERE section_id = ?",
        [section_id],
    )
    if count > 0:
        raise ValueError(
            f"Cannot delete section {section_id}: it still has {count} document(s). "
            "Delete all documents first."
        )
    db.execute("DELETE FROM administration_sections WHERE id = ?", [section_id])


def create_administration_document(  # noqa: PLR0913 — one parameter per column
    db: Connection,
    section_id: int,
    display_name: str,
    filename: str,
    file_type: str,
    sort_order: int = 0,
    uploaded_by_id: int | None = None,
) -> AdministrationDocument:
    """Record an uploaded document and return it."""
    db.execute(
        "INSERT INTO administration_documents"
        " (section_id, display_name, filename, file_type, sort_order, uploaded_by_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [section_id, display_name, filename, file_type, sort_order, uploaded_by_id],
    )
    row = fetch_one(
        db,
        _DocumentRow,
        f"{_DOCUMENT_SELECT} WHERE d.section_id = ?"  # noqa: S608
        " ORDER BY d.uploaded_at DESC LIMIT 1",
        [section_id],
    )
    return require(row, "administration document").to_document()


def delete_administration_document(
    db: Connection, doc_id: int
) -> DeletedDocument | None:
    """Delete a document record, returning where its file is stored."""
    row = fetch_one(db, _DocumentRow, f"{_DOCUMENT_SELECT} WHERE d.id = ?", [doc_id])  # noqa: S608
    if row is None:
        return None
    db.execute("DELETE FROM administration_documents WHERE id = ?", [doc_id])
    return DeletedDocument(filename=row.filename, section_slug=row.section_slug)
