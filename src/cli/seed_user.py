"""
CLI script to add a user to the database.

Usage:
    python -m cli.seed_user <username> <password> [--role admin|content_creator]

Examples:
    python -m cli.seed_user alice mysecretpassword --role admin
    python -m cli.seed_user bob anotherpassword --role content_creator
"""

import argparse
import sys
from pathlib import Path

import duckdb

from website.auth import hash_password
from website.database import _get_db_path, run_migrations
from website.models import User, UserRole
from website import repository


def _add_user(
    con: duckdb.DuckDBPyConnection,
    username: str,
    password: str,
    role: UserRole,
) -> User:
    """Add a user to the database.

    Raises ValueError if a user with that username already exists.
    """
    if repository.get_user_by_username(con, username):
        raise ValueError(f"User '{username}' already exists.")
    return repository.create_user(con, username, hash_password(password), role)


def add_user(username: str, password: str, role: UserRole) -> None:
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        try:
            user = _add_user(con, username, password, role)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        print(f"User '{user.username}' created with role '{user.role.value}'.")
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a user to the database.")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument(
        "--role",
        choices=[r.value for r in UserRole],
        default=UserRole.admin.value,
        help="User role (default: admin)",
    )
    args = parser.parse_args()
    add_user(args.username, args.password, UserRole(args.role))
