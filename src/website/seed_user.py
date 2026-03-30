"""
CLI script to add a user to the database.

Usage:
    python -m website.seed_user <username> <password> [--role admin|content_creator]

Examples:
    python -m website.seed_user alice mysecretpassword --role admin
    python -m website.seed_user bob anotherpassword --role content_creator
"""

import argparse
import sys
from pathlib import Path

import duckdb

from website.auth import hash_password
from website.database import _get_db_path, run_migrations
from website.models import UserRole
from website import repository


def add_user(username: str, password: str, role: UserRole) -> None:
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        existing = repository.get_user_by_username(con, username)
        if existing:
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)
        repository.create_user(con, username, hash_password(password), role)
        print(f"User '{username}' created with role '{role.value}'.")
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
