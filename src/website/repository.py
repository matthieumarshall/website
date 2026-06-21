import json
import re as _re
import duckdb

from website.models import (
    AdministrationDocument,
    AdministrationSection,
    AthleteEntryRow,
    Club,
    ClubManager,
    EntryBatch,
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
        source_pdf=row[12] if len(row) > 12 else None,
    )


def count_fixtures_for_season(db: duckdb.DuckDBPyConnection, season_id: int) -> int:
    result = db.execute(
        "SELECT COUNT(*) FROM fixtures WHERE season_id = ?", [season_id]
    ).fetchone()
    return result[0] if result else 0


_FIXTURE_SELECT = (
    "SELECT id, season_id, title, date, location_name, address, timetable,"
    " travel_instructions, created_at, latitude, longitude, what3words, source_pdf"
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


def set_fixture_source_pdf(
    db: duckdb.DuckDBPyConnection, fixture_id: int, source_pdf: str | None
) -> None:
    """Store the relative path of the original results PDF for *fixture_id*.

    *source_pdf* must be a path relative to ``data/original_website/files/results/``.
    Pass ``None`` to clear the field.
    """
    db.execute(
        "UPDATE fixtures SET source_pdf = ? WHERE id = ?",
        [source_pdf, fixture_id],
    )


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


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


def load_individual_standings(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    category: str | None = None,
) -> list[dict]:
    """Return individual standings rows for a season, optionally filtered by category.

    Each row is a plain dict with keys matching the ``individual_standings`` columns.
    """
    if category is not None:
        rows = db.execute(
            "SELECT id, season_id, category, position, athlete_name, club,"
            " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
            " FROM individual_standings"
            " WHERE season_id = ? AND category = ?"
            " ORDER BY position ASC",
            [season_id, category],
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, season_id, category, position, athlete_name, club,"
            " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
            " FROM individual_standings"
            " WHERE season_id = ?"
            " ORDER BY category ASC, position ASC",
            [season_id],
        ).fetchall()
    cols = [
        "id",
        "season_id",
        "category",
        "position",
        "athlete_name",
        "club",
        "total_score",
        "rounds_competed",
        "fixture_scores",
        "is_imported",
        "updated_at",
    ]
    return [dict(zip(cols, row)) for row in rows]


def load_team_standings(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    category: str | None = None,
) -> list[dict]:
    """Return team standings rows for a season, optionally filtered by category."""
    if category is not None:
        rows = db.execute(
            "SELECT id, season_id, category, position, team_name, club, team_label,"
            " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
            " FROM team_standings"
            " WHERE season_id = ? AND category = ?"
            " ORDER BY position ASC",
            [season_id, category],
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, season_id, category, position, team_name, club, team_label,"
            " total_score, rounds_competed, fixture_scores, is_imported, updated_at"
            " FROM team_standings"
            " WHERE season_id = ?"
            " ORDER BY category ASC, position ASC",
            [season_id],
        ).fetchall()
    cols = [
        "id",
        "season_id",
        "category",
        "position",
        "team_name",
        "club",
        "team_label",
        "total_score",
        "rounds_competed",
        "fixture_scores",
        "is_imported",
        "updated_at",
    ]
    return [dict(zip(cols, row)) for row in rows]


def list_standing_categories(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
) -> list[dict]:
    """Return distinct categories that have standings for *season_id*.

    Each item has keys ``category`` (str), ``type`` ("individual" | "team"),
    and ``count`` (int).
    """
    rows = db.execute(
        "SELECT category, 'individual' AS type, COUNT(*) AS count"
        " FROM individual_standings WHERE season_id = ? GROUP BY category"
        " UNION ALL"
        " SELECT category, 'team' AS type, COUNT(*) AS count"
        " FROM team_standings WHERE season_id = ? GROUP BY category"
        " ORDER BY type ASC, category ASC",
        [season_id, season_id],
    ).fetchall()
    return [{"category": r[0], "type": r[1], "count": r[2]} for r in rows]


def season_has_standings(db: duckdb.DuckDBPyConnection, season_id: int) -> bool:
    """Return True if any standings rows (calculated or imported) exist for the season."""
    row = db.execute(
        "SELECT COUNT(*) FROM individual_standings WHERE season_id = ?",
        [season_id],
    ).fetchone()
    if row and row[0] > 0:
        return True
    row = db.execute(
        "SELECT COUNT(*) FROM team_standings WHERE season_id = ?",
        [season_id],
    ).fetchone()
    return bool(row and row[0] > 0)


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


# ---------------------------------------------------------------------------
# Administration documents
# ---------------------------------------------------------------------------


def _row_to_admin_document(row: tuple, section_slug: str) -> AdministrationDocument:
    doc_id, section_id, display_name, filename, file_type, sort_order = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5],
    )
    href = f"/uploads/administration/{section_slug}/{filename}"
    return AdministrationDocument(
        id=doc_id,
        section_id=section_id,
        display_name=display_name,
        filename=filename,
        href=href,
        file_type=file_type,
        sort_order=sort_order,
    )


def list_administration_sections(
    db: duckdb.DuckDBPyConnection,
) -> list[AdministrationSection]:
    section_rows = db.execute(
        "SELECT id, slug, title, description, sort_order"
        " FROM administration_sections ORDER BY sort_order ASC, title ASC"
    ).fetchall()
    sections: list[AdministrationSection] = []
    for s_row in section_rows:
        s_id, slug, title, description, s_order = (
            s_row[0],
            s_row[1],
            s_row[2],
            s_row[3],
            s_row[4],
        )
        doc_rows = db.execute(
            "SELECT id, section_id, display_name, filename, file_type, sort_order"
            " FROM administration_documents WHERE section_id = ?"
            " ORDER BY sort_order DESC, display_name ASC",
            [s_id],
        ).fetchall()
        documents = [_row_to_admin_document(r, slug) for r in doc_rows]
        sections.append(
            AdministrationSection(
                id=s_id,
                slug=slug,
                title=title,
                description=description,
                sort_order=s_order,
                documents=documents,
            )
        )
    return sections


def get_administration_section(
    db: duckdb.DuckDBPyConnection, section_id: int
) -> AdministrationSection | None:
    row = db.execute(
        "SELECT id, slug, title, description, sort_order"
        " FROM administration_sections WHERE id = ?",
        [section_id],
    ).fetchone()
    if row is None:
        return None
    s_id, slug, title, description, s_order = (row[0], row[1], row[2], row[3], row[4])
    doc_rows = db.execute(
        "SELECT id, section_id, display_name, filename, file_type, sort_order"
        " FROM administration_documents WHERE section_id = ?"
        " ORDER BY sort_order DESC, display_name ASC",
        [s_id],
    ).fetchall()
    documents = [_row_to_admin_document(r, slug) for r in doc_rows]
    return AdministrationSection(
        id=s_id,
        slug=slug,
        title=title,
        description=description,
        sort_order=s_order,
        documents=documents,
    )


def create_administration_section(
    db: duckdb.DuckDBPyConnection,
    slug: str,
    title: str,
    description: str,
    sort_order: int = 0,
) -> AdministrationSection:
    db.execute(
        "INSERT INTO administration_sections (slug, title, description, sort_order)"
        " VALUES (?, ?, ?, ?)",
        [slug, title, description, sort_order],
    )
    row = db.execute(
        "SELECT id, slug, title, description, sort_order"
        " FROM administration_sections WHERE slug = ?",
        [slug],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    return AdministrationSection(
        id=row[0],
        slug=row[1],
        title=row[2],
        description=row[3],
        sort_order=row[4],
        documents=[],
    )


def delete_administration_section(
    db: duckdb.DuckDBPyConnection, section_id: int
) -> None:
    row = db.execute(
        "SELECT COUNT(*) FROM administration_documents WHERE section_id = ?",
        [section_id],
    ).fetchone()
    count: int = row[0] if row is not None else 0
    if count > 0:
        raise ValueError(
            f"Cannot delete section {section_id}: it still has {count} document(s). "
            "Delete all documents first."
        )
    db.execute("DELETE FROM administration_sections WHERE id = ?", [section_id])


def create_administration_document(
    db: duckdb.DuckDBPyConnection,
    section_id: int,
    display_name: str,
    filename: str,
    file_type: str,
    sort_order: int = 0,
    uploaded_by_id: int | None = None,
) -> AdministrationDocument:
    db.execute(
        "INSERT INTO administration_documents"
        " (section_id, display_name, filename, file_type, sort_order, uploaded_by_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [section_id, display_name, filename, file_type, sort_order, uploaded_by_id],
    )
    row = db.execute(
        "SELECT id, section_id, display_name, filename, file_type, sort_order"
        " FROM administration_documents"
        " WHERE section_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        [section_id],
    ).fetchone()
    assert row is not None  # noqa: S101 # nosec B101 — just inserted
    section = get_administration_section(db, section_id)
    slug = section.slug if section else str(section_id)
    return _row_to_admin_document(row, slug)


def delete_administration_document(
    db: duckdb.DuckDBPyConnection, doc_id: int
) -> dict | None:
    """Delete a document record. Returns {filename, section_slug} for disk deletion, or None."""
    row = db.execute(
        "SELECT d.filename, s.slug"
        " FROM administration_documents d"
        " JOIN administration_sections s ON s.id = d.section_id"
        " WHERE d.id = ?",
        [doc_id],
    ).fetchone()
    if row is None:
        return None
    filename: str = row[0]
    section_slug: str = row[1]
    db.execute("DELETE FROM administration_documents WHERE id = ?", [doc_id])
    return {"filename": filename, "section_slug": section_slug}


# ---------------------------------------------------------------------------
# Users (additional lookup)
# ---------------------------------------------------------------------------


def get_user_by_id(db: duckdb.DuckDBPyConnection, user_id: int) -> User | None:
    row = db.execute(
        "SELECT id, username, hashed_password, role FROM users WHERE id = ?",
        [user_id],
    ).fetchone()
    if row is None:
        return None
    return User(id=row[0], username=row[1], hashed_password=row[2], role=row[3])


# ---------------------------------------------------------------------------
# Clubs
# ---------------------------------------------------------------------------


def list_clubs(db: duckdb.DuckDBPyConnection) -> list[Club]:
    rows = db.execute(
        "SELECT id, name, oxl_code, ea_club_id, is_active FROM clubs ORDER BY name"
    ).fetchall()
    return [
        Club(id=r[0], name=r[1], oxl_code=r[2], ea_club_id=r[3], is_active=r[4])
        for r in rows
    ]


def get_club_by_id(club_id: int, db: duckdb.DuckDBPyConnection) -> Club | None:
    row = db.execute(
        "SELECT id, name, oxl_code, ea_club_id, is_active FROM clubs WHERE id = ?",
        [club_id],
    ).fetchone()
    if row is None:
        return None
    return Club(
        id=row[0], name=row[1], oxl_code=row[2], ea_club_id=row[3], is_active=row[4]
    )


def create_club(
    db: duckdb.DuckDBPyConnection,
    name: str,
    oxl_code: str,
    ea_club_id: str,
) -> Club:
    db.execute(
        "INSERT INTO clubs (name, oxl_code, ea_club_id) VALUES (?, ?, ?)",
        [name, oxl_code, ea_club_id],
    )
    row = db.execute(
        "SELECT id, name, oxl_code, ea_club_id, is_active FROM clubs WHERE oxl_code = ?",
        [oxl_code],
    ).fetchone()
    assert row is not None  # noqa: S101
    return Club(
        id=row[0], name=row[1], oxl_code=row[2], ea_club_id=row[3], is_active=row[4]
    )


def update_club(
    db: duckdb.DuckDBPyConnection,
    club_id: int,
    name: str,
    oxl_code: str,
    ea_club_id: str,
    is_active: bool,
) -> None:
    db.execute(
        "UPDATE clubs SET name = ?, oxl_code = ?, ea_club_id = ?, is_active = ? WHERE id = ?",
        [name, oxl_code, ea_club_id, is_active, club_id],
    )


def club_has_active_batches(db: duckdb.DuckDBPyConnection, club_id: int) -> bool:
    row = db.execute(
        "SELECT COUNT(*) FROM entry_batches WHERE club_id = ? AND status IN ('pending_payment', 'payment_initiated', 'paid')",
        [club_id],
    ).fetchone()
    return bool(row and row[0] > 0)


# ---------------------------------------------------------------------------
# Club Managers
# ---------------------------------------------------------------------------


def list_club_managers(db: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = db.execute(
        """
        SELECT cm.id, cm.user_id, cm.club_id, cm.is_active, c.name AS club_name,
               u.username, cm.email
        FROM club_managers cm
        JOIN clubs c ON c.id = cm.club_id
        JOIN users u ON u.id = cm.user_id
        ORDER BY c.name, u.username
        """
    ).fetchall()
    return [
        {
            "manager_id": r[0],
            "user_id": r[1],
            "club_id": r[2],
            "is_active": r[3],
            "club_name": r[4],
            "username": r[5],
            "email": r[6],
        }
        for r in rows
    ]


def get_club_for_manager(
    user_id: int, db: duckdb.DuckDBPyConnection
) -> ClubManager | None:
    row = db.execute(
        """
        SELECT cm.id, cm.user_id, cm.club_id, cm.is_active, c.name
        FROM club_managers cm
        JOIN clubs c ON c.id = cm.club_id
        WHERE cm.user_id = ?
        """,
        [user_id],
    ).fetchone()
    if row is None:
        return None
    return ClubManager(
        id=row[0], user_id=row[1], club_id=row[2], is_active=row[3], club_name=row[4]
    )


def create_club_manager(
    db: duckdb.DuckDBPyConnection,
    user_id: int,
    club_id: int,
    email: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO club_managers (user_id, club_id, email) VALUES (?, ?, ?)",
        [user_id, club_id, email],
    )


def get_club_manager_email(user_id: int, db: duckdb.DuckDBPyConnection) -> str | None:
    row = db.execute(
        "SELECT email FROM club_managers WHERE user_id = ?", [user_id]
    ).fetchone()
    if row is None:
        return None
    return row[0]


def toggle_club_manager_active(db: duckdb.DuckDBPyConnection, manager_id: int) -> bool:
    """Flip is_active for a club_managers row. Returns the new value."""
    row = db.execute(
        "SELECT is_active FROM club_managers WHERE id = ?", [manager_id]
    ).fetchone()
    if row is None:
        return False
    new_val = not row[0]
    db.execute(
        "UPDATE club_managers SET is_active = ? WHERE id = ?", [new_val, manager_id]
    )
    return new_val


# ---------------------------------------------------------------------------
# Season Entry Config & Price Tiers
# ---------------------------------------------------------------------------


def get_season_entry_config(
    season_id: int, db: duckdb.DuckDBPyConnection
) -> dict | None:
    row = db.execute(
        "SELECT season_id, entries_open, ea_reference_date, total_fixtures, junior_pence_per_fixture, adult_pence_per_fixture FROM season_entry_config WHERE season_id = ?",
        [season_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "season_id": row[0],
        "entries_open": row[1],
        "ea_reference_date": row[2],
        "total_fixtures": row[3],
        "junior_pence_per_fixture": row[4],
        "adult_pence_per_fixture": row[5],
    }


def upsert_season_entry_config(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    entries_open: bool,
    ea_reference_date: str,
    total_fixtures: int,
    junior_pence_per_fixture: int = 0,
    adult_pence_per_fixture: int = 0,
) -> None:
    existing = db.execute(
        "SELECT season_id FROM season_entry_config WHERE season_id = ?", [season_id]
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE season_entry_config
            SET entries_open = ?, ea_reference_date = ?, total_fixtures = ?,
                junior_pence_per_fixture = ?, adult_pence_per_fixture = ?
            WHERE season_id = ?
            """,
            [
                entries_open,
                ea_reference_date,
                total_fixtures,
                junior_pence_per_fixture,
                adult_pence_per_fixture,
                season_id,
            ],
        )
    else:
        db.execute(
            "INSERT INTO season_entry_config (season_id, entries_open, ea_reference_date, total_fixtures, junior_pence_per_fixture, adult_pence_per_fixture) VALUES (?, ?, ?, ?, ?, ?)",
            [
                season_id,
                entries_open,
                ea_reference_date,
                total_fixtures,
                junior_pence_per_fixture,
                adult_pence_per_fixture,
            ],
        )


# ---------------------------------------------------------------------------
# Entry Batches
# ---------------------------------------------------------------------------


def create_entry_batch(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    club_id: int,
    manager_user_id: int,
    fixtures_remaining_at_entry: int,
    total_pence: int,
) -> EntryBatch:
    db.execute(
        """
        INSERT INTO entry_batches
            (season_id, club_id, manager_user_id, fixtures_remaining_at_entry, total_pence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [season_id, club_id, manager_user_id, fixtures_remaining_at_entry, total_pence],
    )
    row = db.execute(
        """
        SELECT id, season_id, club_id, manager_user_id, status,
               fixtures_remaining_at_entry, total_pence,
               stripe_checkout_session_id, stripe_payment_intent_id,
               stripe_payment_method, paid_at, created_at
        FROM entry_batches
        WHERE season_id = ? AND club_id = ? AND manager_user_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        [season_id, club_id, manager_user_id],
    ).fetchone()
    assert row is not None  # noqa: S101
    return _row_to_entry_batch(row)


def get_entry_batch(batch_id: int, db: duckdb.DuckDBPyConnection) -> EntryBatch | None:
    row = db.execute(
        """
        SELECT id, season_id, club_id, manager_user_id, status,
               fixtures_remaining_at_entry, total_pence,
               stripe_checkout_session_id, stripe_payment_intent_id,
               stripe_payment_method, paid_at, created_at
        FROM entry_batches WHERE id = ?
        """,
        [batch_id],
    ).fetchone()
    return _row_to_entry_batch(row) if row else None


def get_entry_batch_by_stripe_session(
    session_id: str, db: duckdb.DuckDBPyConnection
) -> EntryBatch | None:
    row = db.execute(
        """
        SELECT id, season_id, club_id, manager_user_id, status,
               fixtures_remaining_at_entry, total_pence,
               stripe_checkout_session_id, stripe_payment_intent_id,
               stripe_payment_method, paid_at, created_at
        FROM entry_batches WHERE stripe_checkout_session_id = ?
        """,
        [session_id],
    ).fetchone()
    return _row_to_entry_batch(row) if row else None


def _row_to_entry_batch(row: tuple) -> EntryBatch:
    return EntryBatch(
        id=row[0],
        season_id=row[1],
        club_id=row[2],
        manager_user_id=row[3],
        status=row[4],
        fixtures_remaining_at_entry=row[5],
        total_pence=row[6],
        stripe_checkout_session_id=row[7],
        stripe_payment_intent_id=row[8],
        stripe_payment_method=row[9],
        paid_at=row[10],
        created_at=row[11],
    )


def update_batch_status(
    db: duckdb.DuckDBPyConnection,
    batch_id: int,
    status: str,
    stripe_payment_intent_id: str | None = None,
    stripe_payment_method: str | None = None,
) -> None:
    if status == "paid":
        db.execute(
            """
            UPDATE entry_batches
            SET status = ?, paid_at = current_timestamp,
                stripe_payment_intent_id = COALESCE(?, stripe_payment_intent_id),
                stripe_payment_method = COALESCE(?, stripe_payment_method)
            WHERE id = ?
            """,
            [status, stripe_payment_intent_id, stripe_payment_method, batch_id],
        )
    else:
        db.execute(
            """
            UPDATE entry_batches
            SET status = ?,
                stripe_payment_intent_id = COALESCE(?, stripe_payment_intent_id),
                stripe_payment_method = COALESCE(?, stripe_payment_method)
            WHERE id = ?
            """,
            [status, stripe_payment_intent_id, stripe_payment_method, batch_id],
        )


def set_batch_stripe_session(
    db: duckdb.DuckDBPyConnection, batch_id: int, session_id: str
) -> None:
    db.execute(
        "UPDATE entry_batches SET stripe_checkout_session_id = ? WHERE id = ?",
        [session_id, batch_id],
    )


def list_entry_batches_for_season(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    club_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """Return batches with club name and manager username joined."""
    where_parts = ["eb.season_id = ?"]
    params: list = [season_id]
    if club_id is not None:
        where_parts.append("eb.club_id = ?")
        params.append(club_id)
    if status is not None:
        where_parts.append("eb.status = ?")
        params.append(status)
    where = " AND ".join(where_parts)
    rows = db.execute(
        f"""
        SELECT eb.id, eb.club_id, c.name AS club_name, u.username AS manager_username,
               eb.status, eb.fixtures_remaining_at_entry, eb.total_pence,
               eb.stripe_payment_method, eb.paid_at, eb.created_at, eb.season_id
        FROM entry_batches eb
        JOIN clubs c ON c.id = eb.club_id
        JOIN users u ON u.id = eb.manager_user_id
        WHERE {where}
        ORDER BY eb.created_at DESC
        """,  # noqa: S608  # nosec B608 — `where` is built from hardcoded clause strings only; user values go into `params`
        params,
    ).fetchall()
    return [
        {
            "id": r[0],
            "club_id": r[1],
            "club_name": r[2],
            "manager_username": r[3],
            "status": r[4],
            "fixtures_remaining_at_entry": r[5],
            "total_pence": r[6],
            "stripe_payment_method": r[7],
            "paid_at": r[8],
            "created_at": r[9],
            "season_id": r[10],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Athlete Entries
# ---------------------------------------------------------------------------


def get_entered_ea_urns(
    season_id: int, club_id: int, db: duckdb.DuckDBPyConnection
) -> set[int]:
    """Return EA URNs already entered by this club this season (any batch status)."""
    rows = db.execute(
        "SELECT ea_urn FROM athlete_entries WHERE season_id = ? AND club_id = ?",
        [season_id, club_id],
    ).fetchall()
    return {r[0] for r in rows}


def create_athlete_entries(
    db: duckdb.DuckDBPyConnection,
    batch_id: int,
    season_id: int,
    club_id: int,
    athletes: list[AthleteEntryRow],
) -> None:
    for athlete in athletes:
        db.execute(
            """
            INSERT INTO athlete_entries
                (batch_id, season_id, club_id, ea_urn, athlete_name, date_of_birth,
                 ea_age_category, is_junior, amount_pence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                batch_id,
                season_id,
                club_id,
                athlete.ea_urn,
                athlete.athlete_name,
                athlete.date_of_birth,
                athlete.ea_age_category,
                athlete.is_junior,
                athlete.amount_pence,
            ],
        )


def get_athlete_entries_for_batch(
    batch_id: int, db: duckdb.DuckDBPyConnection
) -> list[AthleteEntryRow]:
    rows = db.execute(
        """
        SELECT ea_urn, athlete_name, date_of_birth, ea_age_category,
               is_junior, amount_pence, race_number
        FROM athlete_entries WHERE batch_id = ? ORDER BY id
        """,
        [batch_id],
    ).fetchall()
    return [
        AthleteEntryRow(
            ea_urn=r[0],
            athlete_name=r[1],
            date_of_birth=r[2],
            ea_age_category=r[3],
            is_junior=r[4],
            amount_pence=r[5],
            race_number=r[6],
        )
        for r in rows
    ]


def list_athlete_entries_for_season(
    season_id: int, db: duckdb.DuckDBPyConnection
) -> list[dict]:
    """Return all paid/payment_initiated entries for a season, with club name."""
    rows = db.execute(
        """
        SELECT ae.ea_urn, ae.athlete_name, ae.ea_age_category, ae.race_number,
               c.name AS club_name, c.id AS club_id
        FROM athlete_entries ae
        JOIN entry_batches eb ON eb.id = ae.batch_id
        JOIN clubs c ON c.id = ae.club_id
        WHERE ae.season_id = ? AND eb.status IN ('paid', 'payment_initiated')
        ORDER BY c.name, ae.ea_age_category, ae.athlete_name
        """,
        [season_id],
    ).fetchall()
    return [
        {
            "ea_urn": r[0],
            "athlete_name": r[1],
            "ea_age_category": r[2],
            "race_number": r[3],
            "club_name": r[4],
            "club_id": r[5],
        }
        for r in rows
    ]


def assign_race_numbers(batch_id: int, db: duckdb.DuckDBPyConnection) -> None:
    """Assign sequential race numbers to all athletes in a batch that lack one."""
    # Find the season for this batch
    row = db.execute(
        "SELECT season_id FROM entry_batches WHERE id = ?", [batch_id]
    ).fetchone()
    if row is None:
        return
    season_id = row[0]

    # Find current max race number in the season
    max_row = db.execute(
        "SELECT COALESCE(MAX(race_number), 0) FROM athlete_entries WHERE season_id = ?",
        [season_id],
    ).fetchone()
    next_number = (max_row[0] if max_row else 0) + 1

    # Assign to this batch's athletes in insertion order
    athlete_ids = db.execute(
        "SELECT id FROM athlete_entries WHERE batch_id = ? AND race_number IS NULL ORDER BY id",
        [batch_id],
    ).fetchall()
    for (ae_id,) in athlete_ids:
        db.execute(
            "UPDATE athlete_entries SET race_number = ? WHERE id = ?",
            [next_number, ae_id],
        )
        next_number += 1


# ---------------------------------------------------------------------------
# Club Allocations
# ---------------------------------------------------------------------------


def upsert_club_allocation(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    club_id: int,
    allocated_slots: int,
) -> None:
    """Insert or update club's athlete entry allocation for a season."""
    if allocated_slots <= 0:
        raise ValueError("allocated_slots must be greater than 0")
    db.execute(
        """
        INSERT INTO club_allocations (season_id, club_id, allocated_slots, created_at, updated_at)
        VALUES (?, ?, ?, now(), now())
        ON CONFLICT(season_id, club_id) DO UPDATE SET
            allocated_slots = excluded.allocated_slots,
            updated_at = now()
        """,
        [season_id, club_id, allocated_slots],
    )


def get_club_allocation(
    db: duckdb.DuckDBPyConnection, season_id: int, club_id: int
) -> int | None:
    """Return allocated slots for a club in a season, or None if not set."""
    row = db.execute(
        "SELECT allocated_slots FROM club_allocations WHERE season_id = ? AND club_id = ?",
        [season_id, club_id],
    ).fetchone()
    return row[0] if row else None


def get_club_athlete_count(
    db: duckdb.DuckDBPyConnection, season_id: int, club_id: int
) -> int:
    """Count paid athlete entries for a club in a season."""
    row = db.execute(
        """
        SELECT COUNT(ae.id)
        FROM athlete_entries ae
        JOIN entry_batches eb ON eb.id = ae.batch_id
        WHERE ae.season_id = ? AND ae.club_id = ? AND eb.status = 'paid'
        """,
        [season_id, club_id],
    ).fetchone()
    return row[0] if row else 0


def update_athlete_race_number(
    db: duckdb.DuckDBPyConnection, athlete_id: int, race_number: int
) -> None:
    """Update an athlete's race number."""
    if race_number <= 0:
        raise ValueError("race_number must be greater than 0")
    db.execute(
        "UPDATE athlete_entries SET race_number = ? WHERE id = ?",
        [race_number, athlete_id],
    )
