"""Editable rich-text pages: rules, administration guides and news posts."""

from website import repository
from website.content import ADMIN_GUIDES, RULES_PAGE_SLUG, AdminGuide
from website.db import Connection
from website.models import PaginatedPosts, Post, PostCreate
from website.models.forms import PostForm
from website.richtext import sanitise_html
from website.services._common import found


class PageService:
    """Read and replace the sanitised HTML of static pages."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def content(self, slug: str) -> str:
        """Return a page's HTML ("" if it has never been saved)."""
        page = repository.get_static_page(self._db, slug)
        return page.content if page else ""

    def save(self, slug: str, raw_html: str, author_id: int | None) -> None:
        """Sanitise and store a page's HTML."""
        repository.upsert_static_page(
            self._db, slug, sanitise_html(raw_html), author_id
        )

    def rules(self) -> str:
        """Return the rules and constitution HTML."""
        return self.content(RULES_PAGE_SLUG)

    def save_rules(self, raw_html: str, author_id: int | None) -> None:
        """Store the rules and constitution HTML."""
        self.save(RULES_PAGE_SLUG, raw_html, author_id)


def get_guide(slug: str) -> AdminGuide:
    """Return an administration guide.

    Raises:
        NotFoundError: If *slug* is not a known guide.
    """
    return found(ADMIN_GUIDES.get(slug), "Page not found")


class PostService:
    """News post listing and editing."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def page(self, page: int) -> PaginatedPosts:
        """Return a page of published posts (pages start at 1)."""
        return repository.list_posts(self._db, page=max(1, page))

    def get(self, post_id: int) -> Post:
        """Return a post.

        Raises:
            NotFoundError: If the post does not exist.
        """
        return found(repository.get_post_by_id(self._db, post_id), "Post not found")

    def create(self, form: PostForm, author_id: int) -> Post:
        """Create a post with sanitised content."""
        validated = PostCreate(title=form.title, content=sanitise_html(form.content))
        return repository.create_post(
            self._db,
            title=validated.title,
            content=validated.content,
            author_id=author_id,
        )

    def update(self, post_id: int, form: PostForm) -> None:
        """Update a post with sanitised content."""
        validated = PostCreate(title=form.title, content=sanitise_html(form.content))
        repository.update_post(
            self._db, post_id=post_id, title=validated.title, content=validated.content
        )

    def delete(self, post_id: int) -> None:
        """Delete a post."""
        repository.delete_post(self._db, post_id)
