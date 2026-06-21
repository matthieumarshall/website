"""Fixtures for Playwright UI tests"""

import os
import secrets
import string
import subprocess
import sys
import time

import duckdb
import pytest
from playwright.sync_api import sync_playwright

from website.auth import hash_password
from website.database import run_migrations
from website import repository
from website.models import UserRole


def generate_random_password(length=12):
    """Generate random password"""
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_random_username(length=8):
    """Generate random username"""
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


@pytest.fixture(scope="session")
def server_process():
    """Start FastAPI server for UI tests"""
    db_path = "test_ui.duckdb"

    # Seed a test user into a fresh DuckDB file
    if os.path.exists(db_path):
        os.remove(db_path)
    con = duckdb.connect(db_path)
    run_migrations(con)
    repository.create_user(
        con,
        "test_user",
        hash_password("TestPassword123!@#"),
        UserRole.content_creator,
    )
    repository.create_user(
        con,
        "admin_user",
        hash_password("AdminPassword123!@#"),
        UserRole.admin,
    )
    # Seed a season and fixture so fixture-related UI tests have data to work with
    season = repository.create_season(con, "UI Test Season 2026")
    fixture = repository.create_fixture(
        con,
        season_id=season.id,
        title="UI Test Fixture",
        date="2026-06-01",
        location_name="Test Venue",
        address="1 Test Road",
        timetable=[],
        travel_instructions="",
    )
    # Seed individual standings so standings UI tests have data to render
    fid = str(fixture.id)
    con.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                "Senior Women",
                1,
                "Alice Smith",
                "Oxford City AC",
                15,
                1,
                f'{{"{fid}": 1}}',
                False,
            ),
            (
                season.id,
                "Senior Women",
                2,
                "Bob Jones",
                "Abingdon AC",
                28,
                1,
                f'{{"{fid}": 2}}',
                False,
            ),
        ],
    )
    # Seed additional individual categories so the tab row-balancing JS is exercised.
    con.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                cat,
                1,
                f"Athlete {cat}",
                "Test Club",
                10,
                1,
                f'{{"{fid}": 1}}',
                False,
            )
            for cat in [
                "MV40",
                "MV50",
                "MV60",
                "SM",
                "U11B",
                "U11G",
                "U13B",
                "U13G",
                "U15B",
                "U15G",
            ]
        ],
    )
    # Seed team standings
    con.execute(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            season.id,
            "Senior Women",
            1,
            "Oxford City AC A",
            "Oxford City AC",
            "A",
            10,
            1,
            f'{{"{fid}": 1}}',
            False,
        ),
    )
    # Seed additional team categories so the team tab group also wraps.
    con.executemany(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                cat,
                1,
                f"Test {cat} A",
                "Test Club",
                "A",
                10,
                1,
                f'{{"{fid}": 1}}',
                False,
            )
            for cat in [
                "Men's Teams D1",
                "Men's Teams D2",
                "U11B",
                "U11G",
                "U13B",
                "U13G",
                "U15B",
                "Women's Teams D1",
            ]
        ],
    )
    # Seed a race and results so results-browsing UI tests have data to render
    race = repository.create_race(con, fixture.id, "Senior Women Race", display_order=1)
    repository.create_result(
        con,
        race_id=race.id,
        position=1,
        athlete_name="Alice Smith",
        time="35:12",
        category="Senior Women",
        gender="F",
        race_number=101,
        category_position=1,
        gender_position=1,
        club="Oxford City AC",
    )
    repository.create_result(
        con,
        race_id=race.id,
        position=2,
        athlete_name="Bob Jones",
        time="36:45",
        category="Senior Men",
        gender="M",
        race_number=202,
        category_position=1,
        gender_position=1,
        club="Abingdon AC",
    )
    # Seed a second fixture so fixture-tab active-state tests can switch rounds
    fixture2 = repository.create_fixture(
        con,
        season_id=season.id,
        title="UI Test Fixture 2",
        date="2026-07-01",
        location_name="Test Venue 2",
        address="2 Test Road",
        timetable=[],
        travel_instructions="",
    )
    race2 = repository.create_race(
        con, fixture2.id, "Senior Men Race 2", display_order=1
    )
    repository.create_result(
        con,
        race_id=race2.id,
        position=1,
        athlete_name="Charlie Brown",
        time="33:00",
        category="Senior Men",
        gender="M",
        race_number=301,
        category_position=1,
        gender_position=1,
        club="Oxford City AC",
    )
    # Seed administration sections so the administration page has data to render
    for i, (slug, title) in enumerate([("notices", "Notices"), ("agendas", "Agendas")]):
        repository.create_administration_section(
            con, slug=slug, title=title, description="", sort_order=i
        )

    # ------------------------------------------------------------------
    # Seed entries domain: club, manager, config, paid batch for receipt tests
    # Use a dedicated season so we don't hit the max-fixtures-per-season limit.
    # ------------------------------------------------------------------
    from datetime import date, timedelta
    from website.models import AthleteEntryRow

    entries_season = repository.create_season(con, "Entries Test Season")

    repository.create_club(con, name="UI Test Club", oxl_code="UTC", ea_club_id="9999")
    row = con.execute("SELECT id FROM clubs WHERE oxl_code='UTC'").fetchone()
    assert row is not None
    ui_club_id = row[0]

    # Club manager user
    con.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        [
            "entries_manager",
            hash_password("ManagerPassword123!@#"),
            UserRole.club_manager.value,
        ],
    )
    row = con.execute(
        "SELECT id FROM users WHERE username='entries_manager'"
    ).fetchone()
    assert row is not None
    manager_user_id = row[0]
    repository.create_club_manager(
        con, user_id=manager_user_id, club_id=ui_club_id, email="mgr@example.com"
    )

    # Entry config: open, future fixtures, with per-fixture prices
    repository.upsert_season_entry_config(
        con,
        season_id=entries_season.id,
        entries_open=True,
        ea_reference_date="2025-08-31",
        total_fixtures=5,
        junior_pence_per_fixture=160,  # £1.60/fixture × 5 = £8.00
        adult_pence_per_fixture=200,  # £2.00/fixture × 5 = £10.00
    )

    # Future fixtures (so compute_fixtures_remaining > 0)
    today = date.today()
    for i in range(5):
        future = today + timedelta(weeks=(i + 1) * 3)
        repository.create_fixture(
            con,
            season_id=entries_season.id,
            title=f"UI Race {i + 1}",
            date=str(future),
            location_name="UI Venue",
            address="1 Test Road",
            timetable=[],
            travel_instructions="",
        )

    # Pre-paid entry batch for receipt tests
    ui_batch = repository.create_entry_batch(
        con,
        season_id=entries_season.id,
        club_id=ui_club_id,
        manager_user_id=manager_user_id,
        fixtures_remaining_at_entry=5,
        total_pence=1800,
    )
    repository.create_athlete_entries(
        con,
        batch_id=ui_batch.id,
        season_id=entries_season.id,
        club_id=ui_club_id,
        athletes=[
            AthleteEntryRow(
                ea_urn=10000001,
                athlete_name="Test Junior",
                date_of_birth=date(2012, 3, 15),
                ea_age_category="U15",
                is_junior=True,
                amount_pence=800,
            ),
            AthleteEntryRow(
                ea_urn=10000002,
                athlete_name="Test Senior",
                date_of_birth=date(1988, 7, 20),
                ea_age_category="Senior",
                is_junior=False,
                amount_pence=1000,
            ),
        ],
    )
    repository.update_batch_status(
        con,
        batch_id=ui_batch.id,
        status="paid",
        stripe_payment_method="card",
    )
    repository.assign_race_numbers(ui_batch.id, con)
    # Expose the batch ID and season ID via env vars so tests can use them
    os.environ["UI_TEST_BATCH_ID"] = str(ui_batch.id)
    os.environ["UI_TEST_SEASON_ID"] = str(entries_season.id)

    con.close()

    # Start uvicorn server in test mode
    env = os.environ.copy()
    env["DATABASE_URL"] = db_path

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "website.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to be ready
    time.sleep(5)

    yield process

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

    # Give the OS a moment to release file handles before removing the DB
    time.sleep(0.5)

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def browser(server_process):
    """Provide Playwright browser context"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        yield page

        page.close()
        context.close()
        browser.close()


@pytest.fixture(scope="session")
def admin_auth_state(server_process):
    """Log in as admin once per session and return the saved cookie/storage state.

    Using session scope means we perform exactly one login for the entire test
    suite, so we never hit the login rate-limit regardless of how many tests
    use the admin_browser fixture.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8000/login")
        page.fill("input[name='username']", "admin_user")
        page.fill("input[name='password']", "AdminPassword123!@#")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        if page.url == "http://localhost:8000/login":
            error_msgs = page.locator(".alert-danger").all_text_contents()
            raise RuntimeError(
                f"Admin login failed. Page still on login. "
                f"Errors: {error_msgs if error_msgs else 'No errors shown'}"
            )

        # Capture authenticated cookies so every test can reuse them
        state = context.storage_state()

        page.close()
        context.close()
        browser.close()

    return state


@pytest.fixture
def admin_browser(server_process, admin_auth_state):
    """Provide a Playwright browser context pre-logged-in as admin.

    Reuses the session-level auth cookies captured by admin_auth_state, so no
    additional login requests are made — avoiding the login rate-limit.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Inject saved cookies — no login request needed
        context = browser.new_context(storage_state=admin_auth_state)
        page = context.new_page()

        yield page

        page.close()
        context.close()
        browser.close()


@pytest.fixture(scope="session")
def manager_auth_state(server_process):
    """Log in as the seeded club manager once per session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8000/login")
        page.fill("input[name='username']", "entries_manager")
        page.fill("input[name='password']", "ManagerPassword123!@#")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        if page.url == "http://localhost:8000/login":
            error_msgs = page.locator(".alert-danger").all_text_contents()
            raise RuntimeError(
                f"Manager login failed. Page still on login. "
                f"Errors: {error_msgs if error_msgs else 'No errors shown'}"
            )

        state = context.storage_state()

        page.close()
        context.close()
        browser.close()

    return state


@pytest.fixture
def manager_browser(server_process, manager_auth_state):
    """Provide a Playwright browser context pre-logged-in as club manager."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=manager_auth_state)
        page = context.new_page()

        yield page

        page.close()
        context.close()
        browser.close()
