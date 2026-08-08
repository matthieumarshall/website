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

from seed_data import seed_full_dataset


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
    seeded = seed_full_dataset(con)
    # Expose the batch ID and season ID via env vars so tests can use them
    os.environ["UI_TEST_BATCH_ID"] = str(seeded.entry_batch_id)
    os.environ["UI_TEST_SEASON_ID"] = str(seeded.entries_season_id)

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
