"""News post persistence."""

from website.db import Connection
from website.models import PaginatedPosts, Post
from website.repository._rows import fetch_all, fetch_count, fetch_one, require

PER_PAGE = 10

_POST_SELECT = """
    SELECT
        p.id, p.title, p.content, p.author_id,
        u.username AS author_username,
        p.created_at, p.updated_at, p.published
    FROM posts p
    JOIN users u ON u.id = p.author_id
"""


def list_posts(
    db: Connection,
    page: int = 1,
    per_page: int = PER_PAGE,
    published_only: bool = True,
) -> PaginatedPosts:
    """Return one page of posts, newest first."""
    # `where` is chosen from two constant strings, never from user input.
    where = "WHERE p.published = true" if published_only else ""
    total = fetch_count(db, f"SELECT COUNT(*) FROM posts p {where}")  # nosec B608
    posts = fetch_all(
        db,
        Post,
        f"{_POST_SELECT} {where} ORDER BY p.created_at DESC LIMIT ? OFFSET ?",  # nosec B608
        [per_page, (page - 1) * per_page],
    )
    return PaginatedPosts.build(posts=posts, page=page, per_page=per_page, total=total)


def get_post_by_id(db: Connection, post_id: int) -> Post | None:
    """Return the post with *post_id*, or None."""
    return fetch_one(db, Post, f"{_POST_SELECT} WHERE p.id = ?", [post_id])


def create_post(db: Connection, title: str, content: str, author_id: int) -> Post:
    """Insert a post and return it."""
    db.execute(
        "INSERT INTO posts (title, content, author_id) VALUES (?, ?, ?)",
        [title, content, author_id],
    )
    post = fetch_one(
        db,
        Post,
        f"{_POST_SELECT} WHERE p.author_id = ? ORDER BY p.created_at DESC LIMIT 1",
        [author_id],
    )
    return require(post, "post")


def update_post(db: Connection, post_id: int, title: str, content: str) -> Post | None:
    """Update a post's title and content, returning the updated post."""
    db.execute(
        "UPDATE posts SET title = ?, content = ?, updated_at = current_timestamp"
        " WHERE id = ?",
        [title, content, post_id],
    )
    return get_post_by_id(db, post_id)


def delete_post(db: Connection, post_id: int) -> bool:
    """Delete a post."""
    db.execute("DELETE FROM posts WHERE id = ?", [post_id])
    return True
