import json
import re as _re
import duckdb

from website.models import (
    Fixture,
    FixtureImage,
    PaginatedPosts,
    Post,
    Race,
    Result,
    Season,
    StaticPage,
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
    ).fetchone()[0]  # type: ignore[index]  # ty:ignore[not-subscriptable]
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
    ).fetchone()[0]  # type: ignore[index]  # ty:ignore[not-subscriptable]
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
        latitude=row[9],
        longitude=row[10],
        what3words=row[11],
    )


def count_fixtures_for_season(db: duckdb.DuckDBPyConnection, season_id: int) -> int:
    result = db.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchone()
    return result[0] if result else 0


_FIXTURE_SELECT = (
    "SELECT id, season_id, title, date, location_name, address, timetable,"
    " travel_instructions, created_at, latitude, longitude, what3words"
    " FROM fixtures"
)


def list_fixtures_for_season(
    db: duckdb.DuckDBPyConnection, season_id: int
) -> list[Fixture]:
    rows = db.execute(
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY date ASC",  # noqa: S608
        [season_id],
    ).fetchall()
    return [_row_to_fixture(r) for r in rows]


def get_fixture_by_id(db: duckdb.DuckDBPyConnection, fixture_id: int) -> Fixture | None:
    row = db.execute(
        f"{_FIXTURE_SELECT} WHERE id = ?",  # noqa: S608
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
    latitude: float | None = None,
    longitude: float | None = None,
    what3words: str | None = None,
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
        " (season_id, title, date, location_name, address, timetable,"
        " travel_instructions, latitude, longitude, what3words)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            season_id,
            title,
            date,
            location_name,
            address,
            timetable_json,
            travel_instructions,
            latitude,
            longitude,
            what3words,
        ],
    )
    row = db.execute(
        f"{_FIXTURE_SELECT} WHERE season_id = ? ORDER BY created_at DESC LIMIT 1",  # noqa: S608
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
    latitude: float | None = None,
    longitude: float | None = None,
    what3words: str | None = None,
) -> Fixture | None:
    timetable_json = json.dumps([e.model_dump() for e in timetable])
    db.execute(
        "UPDATE fixtures SET title = ?, date = ?, location_name = ?, address = ?,"
        " timetable = ?, travel_instructions = ?, latitude = ?, longitude = ?, what3words = ?"
        " WHERE id = ?",
        [
            title,
            date,
            location_name,
            address,
            timetable_json,
            travel_instructions,
            latitude,
            longitude,
            what3words,
            fixture_id,
        ],
    )
    return get_fixture_by_id(db, fixture_id)


def delete_fixture(db: duckdb.DuckDBPyConnection, fixture_id: int) -> bool:
    db.execute("DELETE FROM fixtures WHERE id = ?", [fixture_id])
    return True


# ---------------------------------------------------------------------------
# Fixture images
# ---------------------------------------------------------------------------


def _row_to_fixture_image(row: tuple) -> FixtureImage:
    return FixtureImage(
        id=row[0],
        fixture_id=row[1],
        filename=row[2],
        uploaded_at=row[3],
    )


def list_fixture_images(
    db: duckdb.DuckDBPyConnection, fixture_id: int
) -> list[FixtureImage]:
    rows = db.execute(
        "SELECT id, fixture_id, filename, uploaded_at"
        " FROM fixture_images WHERE fixture_id = ? ORDER BY uploaded_at ASC",
        [fixture_id],
    ).fetchall()
    return [_row_to_fixture_image(r) for r in rows]


def get_fixture_image_by_id(
    db: duckdb.DuckDBPyConnection, image_id: int
) -> FixtureImage | None:
    row = db.execute(
        "SELECT id, fixture_id, filename, uploaded_at FROM fixture_images WHERE id = ?",
        [image_id],
    ).fetchone()
    return _row_to_fixture_image(row) if row else None


def create_fixture_image(
    db: duckdb.DuckDBPyConnection, fixture_id: int, filename: str
) -> FixtureImage:
    db.execute(
        "INSERT INTO fixture_images (fixture_id, filename) VALUES (?, ?)",
        [fixture_id, filename],
    )
    row = db.execute(
        "SELECT id, fixture_id, filename, uploaded_at"
        " FROM fixture_images WHERE fixture_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        [fixture_id],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    return _row_to_fixture_image(row)


def delete_fixture_image(db: duckdb.DuckDBPyConnection, image_id: int) -> str | None:
    """Delete a fixture image record by ID. Returns the filename, or None if not found."""
    row = db.execute(
        "SELECT filename FROM fixture_images WHERE id = ?", [image_id]
    ).fetchone()
    if row is None:
        return None
    filename: str = row[0]
    db.execute("DELETE FROM fixture_images WHERE id = ?", [image_id])
    return filename


# ---------------------------------------------------------------------------
# Races & Results
# ---------------------------------------------------------------------------


def _race_canonical_key(name: str) -> tuple[int, int, str]:
    """Sort key: junior races (U9, U11, …) ordered by age first, then alpha."""
    m = _re.search(r"\bU(\d+)\b", name, _re.IGNORECASE)
    if m:
        return (0, int(m.group(1)), name.lower())
    return (1, 0, name.lower())


def _row_to_race(row: tuple) -> Race:
    return Race(
        id=row[0],
        fixture_id=row[1],
        name=row[2],
        display_order=row[3],
        created_at=row[4],
    )


def _row_to_result(row: tuple) -> Result:
    return Result(
        id=row[0],
        race_id=row[1],
        position=row[2],
        race_number=row[3],
        athlete_name=row[4],
        time=row[5],
        category=row[6],
        category_position=row[7],
        gender=row[8],
        gender_position=row[9],
        club=row[10],
    )


def list_races_for_fixture(
    db: duckdb.DuckDBPyConnection, fixture_id: int
) -> list[Race]:
    rows = db.execute(
        "SELECT id, fixture_id, name, display_order, created_at"
        " FROM races WHERE fixture_id = ?",
        [fixture_id],
    ).fetchall()
    races = [_row_to_race(r) for r in rows]
    return sorted(races, key=lambda r: _race_canonical_key(r.name))


def get_race_by_id(db: duckdb.DuckDBPyConnection, race_id: int) -> Race | None:
    row = db.execute(
        "SELECT id, fixture_id, name, display_order, created_at"
        " FROM races WHERE id = ?",
        [race_id],
    ).fetchone()
    return _row_to_race(row) if row else None


def list_results_for_race(db: duckdb.DuckDBPyConnection, race_id: int) -> list[Result]:
    rows = db.execute(
        "SELECT id, race_id, position, race_number, athlete_name, time,"
        " category, category_position, gender, gender_position, club"
        " FROM results WHERE race_id = ? ORDER BY position ASC",
        [race_id],
    ).fetchall()
    return [_row_to_result(r) for r in rows]


def fixture_has_results(db: duckdb.DuckDBPyConnection, fixture_id: int) -> bool:
    row = db.execute(
        "SELECT COUNT(*) FROM results r"
        " JOIN races rc ON rc.id = r.race_id"
        " WHERE rc.fixture_id = ?",
        [fixture_id],
    ).fetchone()
    return bool(row and row[0] > 0)


def create_race(
    db: duckdb.DuckDBPyConnection,
    fixture_id: int,
    name: str,
    display_order: int = 0,
) -> Race:
    db.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [fixture_id, name, display_order],
    )
    row = db.execute(
        "SELECT id, fixture_id, name, display_order, created_at"
        " FROM races WHERE fixture_id = ? ORDER BY created_at DESC LIMIT 1",
        [fixture_id],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    return _row_to_race(row)


def create_result(
    db: duckdb.DuckDBPyConnection,
    race_id: int,
    position: int,
    athlete_name: str,
    time: str,
    category: str,
    gender: str,
    race_number: int | None = None,
    category_position: int | None = None,
    gender_position: int | None = None,
    club: str | None = None,
) -> Result:
    db.execute(
        "INSERT INTO results"
        " (race_id, position, race_number, athlete_name, time, category,"
        " category_position, gender, gender_position, club)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            race_id,
            position,
            race_number,
            athlete_name,
            time,
            category,
            category_position,
            gender,
            gender_position,
            club,
        ],
    )
    row = db.execute(
        "SELECT id, race_id, position, race_number, athlete_name, time,"
        " category, category_position, gender, gender_position, club"
        " FROM results WHERE race_id = ? ORDER BY id DESC LIMIT 1",
        [race_id],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    return _row_to_result(row)


# ---------------------------------------------------------------------------
# Static Pages
# ---------------------------------------------------------------------------


def _row_to_static_page(row: tuple) -> StaticPage:
    return StaticPage(
        id=row[0],
        slug=row[1],
        content=row[2],
        updated_at=row[3],
        updated_by_id=row[4],
    )


def get_static_page(db: duckdb.DuckDBPyConnection, slug: str) -> StaticPage | None:
    row = db.execute(
        "SELECT id, slug, content, updated_at, updated_by_id"
        " FROM static_pages WHERE slug = ?",
        [slug],
    ).fetchone()
    return _row_to_static_page(row) if row else None


def upsert_static_page(
    db: duckdb.DuckDBPyConnection,
    slug: str,
    content: str,
    updated_by_id: int | None = None,
) -> StaticPage:
    db.execute(
        "INSERT INTO static_pages (slug, content, updated_by_id)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT (slug) DO UPDATE"
        " SET content = excluded.content,"
        "     updated_at = now(),"
        "     updated_by_id = excluded.updated_by_id",
        [slug, content, updated_by_id],
    )
    row = db.execute(
        "SELECT id, slug, content, updated_at, updated_by_id"
        " FROM static_pages WHERE slug = ?",
        [slug],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just upserted
    return _row_to_static_page(row)
