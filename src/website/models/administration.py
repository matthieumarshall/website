"""Administration documents and editable static pages."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AdministrationDocument(BaseModel):
    """A downloadable document within an administration section."""

    model_config = ConfigDict(frozen=True)

    id: int
    section_id: int
    display_name: str
    filename: str
    # /uploads/administration/<section_slug>/<filename>
    href: str
    file_type: str
    sort_order: int


class AdministrationSection(BaseModel):
    """A titled group of administration documents."""

    model_config = ConfigDict(frozen=True)

    id: int
    slug: str  # used for HTML anchors and URL path segments
    title: str
    description: str
    sort_order: int
    documents: list[AdministrationDocument]


class DeletedDocument(BaseModel):
    """Identifies the stored file of a document whose record was deleted."""

    model_config = ConfigDict(frozen=True)

    filename: str
    section_slug: str


class StaticPage(BaseModel):
    """Rich-text content for a page editable by staff."""

    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    content: str
    updated_at: datetime
    updated_by_id: int | None
