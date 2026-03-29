import re
import secrets
import string

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.auth import hash_password
from website.database import get_db, run_migrations
from website.main import app
from website.models import UserRole


def generate_random_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_random_username(length: int = 8) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


@pytest.fixture(scope="function")
def test_db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]
    """Isolated in-memory DuckDB connection with migrations applied."""
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


@pytest.fixture
def test_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_creds() -> dict[str, str]:
    return {
        "username": generate_random_username(),
        "password": generate_random_password(),
    }


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
    client = TestClient(app)

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
def admin_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]
    """TestClient authenticated as an admin user."""
    _, client = _create_user_and_client(test_db, UserRole.admin)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def content_creator_client(test_db: duckdb.DuckDBPyConnection) -> TestClient:  # type: ignore[misc]
    """TestClient authenticated as a content_creator user."""
    _, client = _create_user_and_client(test_db, UserRole.content_creator)
    yield client
    app.dependency_overrides.clear()
