"""User account persistence."""

from website.db import Connection
from website.models import User, UserRole
from website.repository._rows import fetch_one, require

_USER_SELECT = "SELECT id, username, hashed_password, role FROM users"


def get_user_by_username(db: Connection, username: str) -> User | None:
    """Return the user with *username*, or None."""
    return fetch_one(db, User, f"{_USER_SELECT} WHERE username = ?", [username])


def get_user_by_id(db: Connection, user_id: int) -> User | None:
    """Return the user with *user_id*, or None."""
    return fetch_one(db, User, f"{_USER_SELECT} WHERE id = ?", [user_id])


def create_user(
    db: Connection,
    username: str,
    hashed_password: str,
    role: UserRole,
) -> User:
    """Insert a user and return it."""
    db.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        [username, hashed_password, role.value],
    )
    return require(get_user_by_username(db, username), "user")
