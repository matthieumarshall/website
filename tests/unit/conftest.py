import os
import re
import secrets
import string
import uuid

# Set testing mode before importing the app
os.environ["TESTING"] = "true"

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.auth import hash_password
from website.database import get_db, run_migrations
from website.main import app
from website.models import UserRole


@pytest.fixture
def test_db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    """Isolated in-memory DuckDB connection with migrations applied."""
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


@pytest.fixture
def test_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    # Give each test client a unique IP to avoid rate limit collisions
    client = TestClient(app, headers={"X-Forwarded-For": str(uuid.uuid4())})
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_creds() -> dict[str, str]:
    return {
        "username": generate_random_username(),
        "password": generate_random_password(),
    }


def generate_random_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_random_username(length: int = 8) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def _create_user_and_client(
    test_db: duckdb.DuckDBPyConnection,
    role: UserRole,
) -> tuple[dict[str, str], TestClient]:
    username = generate_random_username()
    password = generate_random_password()
    repository.create_user(test_db, username, hash_password(password), role)

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    # Give each client a unique IP to avoid rate limit collisions
    client = TestClient(app, headers={"X-Forwarded-For": str(uuid.uuid4())})

    login_page = client.get("/login")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert match, "No CSRF token found in login form"
    resp = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": match.group(1)},
    )
    assert resp.status_code in (200, 302)
    return {"username": username, "password": password}, client


@pytest.fixture
def test_user(test_db: duckdb.DuckDBPyConnection, test_user_creds: dict[str, str]):
    """Create a content_creator user in the test database."""
    return repository.create_user(
        test_db,
        test_user_creds["username"],
        hash_password(test_user_creds["password"]),
        UserRole.content_creator,
    )


@pytest.fixture
def authenticated_client(
    test_client: TestClient,
    test_user_creds: dict[str, str],
    test_user,  # noqa: ANN001 — ensures user is created first
) -> TestClient:
    login_page = test_client.get("/login")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
    assert match, "No CSRF token found in login form"
    resp = test_client.post(
        "/login",
        data={**test_user_creds, "csrf_token": match.group(1)},
    )
    assert resp.status_code in (200, 302)
    return test_client


@pytest.fixture
def admin_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    """TestClient authenticated as an admin user."""
    _, client = _create_user_and_client(test_db, UserRole.admin)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def content_creator_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    """TestClient authenticated as a content_creator user."""
    _, client = _create_user_and_client(test_db, UserRole.content_creator)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# Import Testing Fixtures (for migrate_results and migrate_standings)
# ============================================================================

# Pytest markers for import tests


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")


@pytest.fixture
def sample_season(test_db: duckdb.DuckDBPyConnection) -> int:
    """Create a sample season for import testing.

    Returns:
        Season ID of created season
    """
    con = test_db
    con.execute("INSERT INTO seasons (name) VALUES (?)", ["2021-2022"])
    result = con.execute("SELECT id FROM seasons WHERE name = '2021-2022'").fetchone()
    assert result is not None, "Season should have been created"
    return int(result[0])


@pytest.fixture
def sample_fixture(test_db: duckdb.DuckDBPyConnection, sample_season: int) -> int:
    """Create a sample fixture for import testing.

    Returns:
        Fixture ID of created fixture
    """
    from datetime import date

    con = test_db
    con.execute(
        "INSERT INTO fixtures (season_id, date, title) VALUES (?, ?, ?)",
        [sample_season, date(2021, 1, 1), "Bicester Heritage"],
    )
    result = con.execute(
        "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
        [sample_season, date(2021, 1, 1)],
    ).fetchone()
    assert result is not None, "Fixture should have been created"
    return int(result[0])


@pytest.fixture
def sample_race(test_db: duckdb.DuckDBPyConnection, sample_fixture: int) -> int:
    """Create a sample race for import testing.

    Returns:
        Race ID of created race
    """
    con = test_db
    con.execute(
        "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
        [sample_fixture, "Men", 5],
    )
    result = con.execute(
        "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
        [sample_fixture, "Men"],
    ).fetchone()
    assert result is not None, "Race should have been created"
    return int(result[0])


class TestDataGenerator:
    """Helper class for generating realistic test data for import tests."""

    @staticmethod
    def create_season(con: duckdb.DuckDBPyConnection, name: str) -> int:
        """Create a season and return its ID.

        Args:
            con: DuckDB connection
            name: Season name (e.g., "2021-2022")

        Returns:
            Season ID
        """
        con.execute("INSERT INTO seasons (name) VALUES (?)", [name])
        result = con.execute("SELECT id FROM seasons WHERE name = ?", [name]).fetchone()
        return int(result[0]) if result else -1

    @staticmethod
    def create_fixture(
        con: duckdb.DuckDBPyConnection,
        season_id: int,
        date_str: str,
        title: str,
    ) -> int:
        """Create a fixture and return its ID.

        Args:
            con: DuckDB connection
            season_id: Season ID
            date_str: Date as YYYY-MM-DD string
            title: Fixture title (venue name)

        Returns:
            Fixture ID
        """
        from datetime import datetime

        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        con.execute(
            "INSERT INTO fixtures (season_id, date, title) VALUES (?, ?, ?)",
            [season_id, date_obj, title],
        )
        result = con.execute(
            "SELECT id FROM fixtures WHERE season_id = ? AND date = ? AND title = ?",
            [season_id, date_obj, title],
        ).fetchone()
        return int(result[0]) if result else -1

    @staticmethod
    def create_race(
        con: duckdb.DuckDBPyConnection,
        fixture_id: int,
        name: str,
        display_order: int = 0,
    ) -> int:
        """Create a race and return its ID.

        Args:
            con: DuckDB connection
            fixture_id: Fixture ID
            name: Race name (e.g., "Men", "U13 Boys")
            display_order: Display order (0=default)

        Returns:
            Race ID
        """
        con.execute(
            "INSERT INTO races (fixture_id, name, display_order) VALUES (?, ?, ?)",
            [fixture_id, name, display_order],
        )
        result = con.execute(
            "SELECT id FROM races WHERE fixture_id = ? AND name = ?",
            [fixture_id, name],
        ).fetchone()
        return int(result[0]) if result else -1

    @staticmethod
    def create_result(
        con: duckdb.DuckDBPyConnection,
        race_id: int,
        position: int,
        athlete_name: str,
        time: str,
        category: str,
        gender: str,
        club: str | None = None,
    ) -> int:
        """Create a result record and return its ID.

        Args:
            con: DuckDB connection
            race_id: Race ID
            position: Finishing position
            athlete_name: Athlete name
            time: Finish time (formatted string)
            category: Category (e.g., "SM40")
            gender: Gender (M, F, etc.)
            club: Club name (optional)

        Returns:
            Result ID
        """
        con.execute(
            "INSERT INTO results (race_id, position, athlete_name, time, category, gender, club) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [race_id, position, athlete_name, time, category, gender, club],
        )
        result = con.execute(
            "SELECT id FROM results WHERE race_id = ? AND athlete_name = ?",
            [race_id, athlete_name],
        ).fetchone()
        return int(result[0]) if result else -1


@pytest.fixture
def test_data_generator() -> TestDataGenerator:
    """Provide test data generator for import tests."""
    return TestDataGenerator()
