"""External link management, shared by the in-page editor and admin pages."""

from pydantic import BaseModel, ConfigDict

from website import repository
from website.content import LINK_CATEGORIES, LINK_CATEGORY_LABELS, LinkCategory
from website.db import Connection
from website.errors import ValidationError
from website.models import ExternalLink
from website.models.forms import LinkForm
from website.richtext import validate_http_url
from website.services._common import blank_to_none, found

_MAX_TITLE_LENGTH = 200


class LinkDetails(BaseModel):
    """Normalised, validated link fields."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    category: str
    description: str | None
    sort_order: int
    is_active: bool


class LinksPage(BaseModel):
    """Links grouped under their category headings."""

    model_config = ConfigDict(frozen=True)

    categories: tuple[LinkCategory, ...]
    links_by_category: dict[str, list[ExternalLink]]


def normalise_link(form: LinkForm) -> LinkDetails:
    """Trim and validate a submitted link.

    Raises:
        ValidationError: If the URL, title, category or order is invalid.
    """
    title = form.title.strip()
    try:
        url = validate_http_url(form.url.strip())
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if (
        not title
        or len(title) > _MAX_TITLE_LENGTH
        or form.category not in LINK_CATEGORY_LABELS
    ):
        raise ValidationError("Title and a valid category are required")
    if form.sort_order < 0:
        raise ValidationError("Display order cannot be negative")
    return LinkDetails(
        title=title,
        url=url,
        category=form.category,
        description=blank_to_none(form.description),
        sort_order=form.sort_order,
        is_active=form.is_active,
    )


class LinkService:
    """Create, edit, toggle and delete external links."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def list_links(self) -> list[ExternalLink]:
        """Return every link, active or not."""
        return repository.list_external_links(self._db)

    def grouped(self, include_inactive: bool) -> LinksPage:
        """Return links grouped by category (inactive ones only for staff)."""
        links_by_category: dict[str, list[ExternalLink]] = {
            category.key: [] for category in LINK_CATEGORIES
        }
        for link in repository.list_external_links(
            self._db, active_only=not include_inactive
        ):
            if link.category in links_by_category:
                links_by_category[link.category].append(link)
        return LinksPage(
            categories=LINK_CATEGORIES, links_by_category=links_by_category
        )

    def get(self, link_id: int) -> ExternalLink:
        """Return a link.

        Raises:
            NotFoundError: If the link does not exist.
        """
        return found(repository.get_external_link(self._db, link_id))

    def create(self, form: LinkForm, honour_active_flag: bool = False) -> ExternalLink:
        """Create a link; new links are active unless the form says otherwise.

        Args:
            form: The submitted link.
            honour_active_flag: If True, an unticked ``is_active`` box creates the
                link hidden (the in-page editor); otherwise it is always active.

        Raises:
            ValidationError: If the submission is invalid.
        """
        details = normalise_link(form)
        try:
            link = repository.create_external_link(
                self._db,
                details.title,
                details.url,
                details.category,
                details.description,
                details.sort_order,
            )
        except (ValueError, repository.IntegrityError) as exc:
            raise ValidationError(str(exc)) from exc
        if honour_active_flag and not details.is_active:
            repository.toggle_external_link(self._db, link.id)
            link = self.get(link.id)
        return link

    def update(self, link_id: int, form: LinkForm) -> ExternalLink:
        """Update a link and return it.

        Raises:
            NotFoundError: If the link does not exist.
            ValidationError: If the submission is invalid.
        """
        self.get(link_id)
        details = normalise_link(form)
        try:
            repository.update_external_link(
                self._db,
                link_id,
                details.title,
                details.url,
                details.category,
                details.description,
                details.sort_order,
                details.is_active,
            )
        except (ValueError, repository.IntegrityError) as exc:
            raise ValidationError(str(exc)) from exc
        return self.get(link_id)

    def toggle_active(self, link_id: int) -> ExternalLink:
        """Flip a link's active flag and return it.

        Raises:
            NotFoundError: If the link does not exist.
        """
        self.get(link_id)
        repository.toggle_external_link(self._db, link_id)
        return self.get(link_id)

    def delete(self, link_id: int) -> None:
        """Delete a link.

        Raises:
            NotFoundError: If the link does not exist.
        """
        self.get(link_id)
        repository.delete_external_link(self._db, link_id)
