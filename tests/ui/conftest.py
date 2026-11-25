"""Fixtures for Playwright UI tests"""

import os
import secrets
import string
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

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

    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError(
                    f"UI server exited early with code {process.returncode}"
                )
            try:
                with urlopen("http://127.0.0.1:8000/", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("UI server did not become ready within 30 seconds")
            time.sleep(0.1)
        yield process
    finally:
        _stop_server(process, db_path)


def _stop_server(process, db_path):
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


@pytest.fixture(scope="session")
def browser_process(server_process):
    """Share Chromium while keeping every test in a fresh context."""
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def browser(browser_process):
    context = browser_process.new_context()
    try:
        yield context.new_page()
    finally:
        context.close()


def _auth_state(browser_process, username, password):
    context = browser_process.new_context()
    try:
        page = context.new_page()
        page.goto("http://localhost:8000/login")
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        page.wait_for_url("http://localhost:8000/news")
        return context.storage_state()
    finally:
        context.close()


@pytest.fixture(scope="session")
def admin_auth_state(browser_process):
    return _auth_state(browser_process, "admin_user", "AdminPassword123!@#")


@pytest.fixture(scope="session")
def manager_auth_state(browser_process):
    return _auth_state(browser_process, "entries_manager", "ManagerPassword123!@#")


@pytest.fixture
def admin_browser(browser_process, admin_auth_state):
    context = browser_process.new_context(storage_state=admin_auth_state)
    try:
        yield context.new_page()
    finally:
        context.close()


@pytest.fixture
def manager_browser(browser_process, manager_auth_state):
    context = browser_process.new_context(storage_state=manager_auth_state)
    try:
        yield context.new_page()
    finally:
        context.close()
