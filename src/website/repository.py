import duckdb

from website.models import PaginatedPosts, Post, User, UserRole

_PER_PAGE = 10


def get_user_by_username(db: duckdb.DuckDBPyConnection, username: str) -> User | None:
    row = db.execute(
        "SELECT id, username, hashed_password, role FROM users WHERE username = ?",
        [username],
    ).fetchone()
    if row is None:
        return None
    return User(id=row[0], username=row[1], hashed_password=row[2], role=row[3])


def create_user(
    db: duckdb.DuckDBPyConnection,
    username: str,
    hashed_password: str,
    role: UserRole,
) -> User:
    db.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        [username, hashed_password, role.value],
    )
    row = db.execute(
        "SELECT id, username, hashed_password, role FROM users WHERE username = ?",
        [username],
    ).fetchone()
    assert row is not None  # noqa: S101 — just inserted; cannot be None
    return User(id=row[0], username=row[1], hashed_password=row[2], role=row[3])


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

_POST_SELECT = """
    SELECT
        p.id, p.title, p.content, p.author_id,
        u.username AS author_username,
        p.created_at, p.updated_at, p.published
    FROM posts p
    JOIN users u ON u.id = p.author_id
"""


def _row_to_post(row: tuple) -> Post:
    return Post(
        id=row[0],
        title=row[1],
        content=row[2],
        author_id=row[3],
        author_username=row[4],
        created_at=row[5],
        updated_at=row[6],
        published=row[7],
    )


def list_posts(
    db: duckdb.DuckDBPyConnection,
    page: int = 1,
    per_page: int = _PER_PAGE,
    published_only: bool = True,
) -> PaginatedPosts:
    where = "WHERE p.published = true" if published_only else ""
    total: int = db.execute(
        f"SELECT COUNT(*) FROM posts p {where}"  # noqa: S608  # nosec B608 — no user data interpolated; `where` is built from a boolean, not user input
    ).fetchone()[0]  # type: ignore[index]
    offset = (page - 1) * per_page
    rows = db.execute(
        f"{_POST_SELECT} {where} ORDER BY p.created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [per_page, offset],
    ).fetchall()
    return PaginatedPosts.build(
        posts=[_row_to_post(r) for r in rows],
        page=page,
        per_page=per_page,
        total=total,
    )


def get_post_by_id(db: duckdb.DuckDBPyConnection, post_id: int) -> Post | None:
    row = db.execute(
        f"{_POST_SELECT} WHERE p.id = ?",  # noqa: S608
        [post_id],
    ).fetchone()
    return _row_to_post(row) if row else None


def create_post(
    db: duckdb.DuckDBPyConnection,
    title: str,
    content: str,
    author_id: int,
) -> Post:
    db.execute(
        "INSERT INTO posts (title, content, author_id) VALUES (?, ?, ?)",
        [title, content, author_id],
    )
    row = db.execute(
        f"{_POST_SELECT} WHERE p.author_id = ? ORDER BY p.created_at DESC LIMIT 1",  # noqa: S608
        [author_id],
    ).fetchone()
    assert row is not None  # noqa: S101 — just inserted
    return _row_to_post(row)


def update_post(
    db: duckdb.DuckDBPyConnection,
    post_id: int,
    title: str,
    content: str,
) -> Post | None:
    db.execute(
        "UPDATE posts SET title = ?, content = ?, updated_at = current_timestamp"
        " WHERE id = ?",
        [title, content, post_id],
    )
    return get_post_by_id(db, post_id)


def delete_post(db: duckdb.DuckDBPyConnection, post_id: int) -> bool:
    db.execute("DELETE FROM posts WHERE id = ?", [post_id])
    return True
