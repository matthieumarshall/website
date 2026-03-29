"""Fixtures for Playwright UI tests"""

import pytest
import subprocess
import sys
import time
import os
import string
import secrets
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]

from website.models import Base, User
from website.auth import hash_password


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
    # Setup test database with test user
    db_path = "test_ui.db"
    engine = create_engine(f"sqlite:///./{db_path}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create test user
    test_user = User(
        username="test_user", hashed_password=hash_password("TestPassword123!@#")
    )
    session.add(test_user)
    session.commit()
    session.close()
    engine.dispose()  # Release all SQLAlchemy connections before starting server

    # Start uvicorn server in test mode
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///./{db_path}"

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

    # Clean up test database
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
