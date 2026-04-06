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


@pytest.fixture
def admin_browser(server_process):
    """Provide a Playwright browser context pre-logged-in as admin"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Log in as admin
        page.goto("http://localhost:8000/login")
        page.fill("input[name='username']", "admin_user")
        page.fill("input[name='password']", "AdminPassword123!@#")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        yield page

        page.close()
        context.close()
        browser.close()
