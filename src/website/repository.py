import json
import duckdb

from website.models import (
    Fixture,
    PaginatedPosts,
    Post,
    Season,
    TimetableEntry,
    User,
    UserRole,
    _MAX_FIXTURES_PER_SEASON,
)

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


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------


def _row_to_season(row: tuple) -> Season:
    return Season(id=row[0], name=row[1], created_at=row[2])


def list_seasons(db: duckdb.DuckDBPyConnection) -> list[Season]:
    rows = db.execute(
        "SELECT id, name, created_at FROM seasons ORDER BY name DESC"
    ).fetchall()
    return [_row_to_season(r) for r in rows]


def get_season_by_id(db: duckdb.DuckDBPyConnection, season_id: int) -> Season | None:
    row = db.execute(
        "SELECT id, name, created_at FROM seasons WHERE id = ?", [season_id]
    ).fetchone()
    return _row_to_season(row) if row else None


def create_season(db: duckdb.DuckDBPyConnection, name: str) -> Season:
    db.execute("INSERT INTO seasons (name) VALUES (?)", [name])
    row = db.execute(
        "SELECT id, name, created_at FROM seasons WHERE name = ?", [name]
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted; cannot be None
    return _row_to_season(row)


def delete_season(db: duckdb.DuckDBPyConnection, season_id: int) -> bool:
    count: int = db.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchone()[0]  # type: ignore[index]
    if count > 0:
        raise ValueError(
            f"Cannot delete season {season_id}: it still has {count} fixture(s). "
            "Delete all fixtures first."
        )
    db.execute("DELETE FROM seasons WHERE id = ?", [season_id])
    return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row_to_fixture(row: tuple) -> Fixture:
    timetable_entries: list[TimetableEntry] = [
        TimetableEntry(**entry) for entry in json.loads(row[6])
    ]
    return Fixture(
        id=row[0],
        season_id=row[1],
        title=row[2],
        date=row[3],
        location_name=row[4],
        address=row[5],
        timetable=timetable_entries,
        travel_instructions=row[7],
        created_at=row[8],
    )


def count_fixtures_for_season(db: duckdb.DuckDBPyConnection, season_id: int) -> int:
    result = db.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchone()
    return result[0] if result else 0  # type: ignore[index]


def list_fixtures_for_season(
    db: duckdb.DuckDBPyConnection, season_id: int
) -> list[Fixture]:
    rows = db.execute(
        "SELECT id, season_id, title, date, location_name, address, timetable,"
        " travel_instructions, created_at"
        " FROM fixtures WHERE season_id = ? ORDER BY date ASC",
        [season_id],
    ).fetchall()
    return [_row_to_fixture(r) for r in rows]


def get_fixture_by_id(db: duckdb.DuckDBPyConnection, fixture_id: int) -> Fixture | None:
    row = db.execute(
        "SELECT id, season_id, title, date, location_name, address, timetable,"
        " travel_instructions, created_at"
        " FROM fixtures WHERE id = ?",
        [fixture_id],
    ).fetchone()
    return _row_to_fixture(row) if row else None


def create_fixture(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    title: str,
    date: str,
    location_name: str,
    address: str,
    timetable: list[TimetableEntry],
    travel_instructions: str,
) -> Fixture:
    current_count = count_fixtures_for_season(db, season_id)
    if current_count >= _MAX_FIXTURES_PER_SEASON:
        raise ValueError(
            f"Season {season_id} already has {current_count} fixtures "
            f"(maximum is {_MAX_FIXTURES_PER_SEASON})."
        )
    timetable_json = json.dumps([e.model_dump() for e in timetable])
    db.execute(
        "INSERT INTO fixtures"
        " (season_id, title, date, location_name, address, timetable, travel_instructions)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            season_id,
            title,
            date,
            location_name,
            address,
            timetable_json,
            travel_instructions,
        ],
    )
    row = db.execute(
        "SELECT id, season_id, title, date, location_name, address, timetable,"
        " travel_instructions, created_at"
        " FROM fixtures WHERE season_id = ? ORDER BY created_at DESC LIMIT 1",
        [season_id],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    return _row_to_fixture(row)


def update_fixture(
    db: duckdb.DuckDBPyConnection,
    fixture_id: int,
    title: str,
    date: str,
    location_name: str,
    address: str,
    timetable: list[TimetableEntry],
    travel_instructions: str,
) -> Fixture | None:
    timetable_json = json.dumps([e.model_dump() for e in timetable])
    db.execute(
        "UPDATE fixtures SET title = ?, date = ?, location_name = ?, address = ?,"
        " timetable = ?, travel_instructions = ? WHERE id = ?",
        [
            title,
            date,
            location_name,
            address,
            timetable_json,
            travel_instructions,
            fixture_id,
        ],
    )
    return get_fixture_by_id(db, fixture_id)


def delete_fixture(db: duckdb.DuckDBPyConnection, fixture_id: int) -> bool:
    db.execute("DELETE FROM fixtures WHERE id = ?", [fixture_id])
    return True
