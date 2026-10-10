"""Interactive CLI script to seed a user into the database with prompts.

Usage:
    uv run python scripts/seed_user_prompt.py
    or
    python scripts/seed_user_prompt.py
"""

import getpass
import sys
from pathlib import Path

# Add src/ to sys.path so modules under src/ are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb

from website import repository
from website.db import get_db_path, run_migrations
from website.models import UserRole
from website.passwords import hash_password


def prompt_and_create_user() -> None:
    print("=== OXL User Seed Tool ===")

    # 1. Prompt for username
    while True:
        username = input("Username: ").strip()
        if username:
            break
        print("Username cannot be empty. Please try again.")

    # 2. Prompt for password (masked input)
    while True:
        password = getpass.getpass("Password: ")
        if not password:
            print("Password cannot be empty. Please try again.")
            continue
        confirm = getpass.getpass("Confirm Password: ")
        if password != confirm:
            print("Passwords do not match. Please try again.\n")
            continue
        break

    # 3. Prompt for role
    valid_roles = [r.value for r in UserRole]
    default_role = UserRole.admin.value
    roles_display = ", ".join(valid_roles)

    role_input = (
        input(f"Role [{roles_display}] (default: {default_role}): ").strip().lower()
    )
    if not role_input:
        role_str = default_role
    else:
        role_str = role_input

    if role_str not in valid_roles:
        print(f"Invalid role '{role_str}'. Allowed roles: {roles_display}")
        sys.exit(1)

    role = UserRole(role_str)

    # 4. Connect to database and insert user
    db_path = get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"\nConnecting to database at: {db_path}")
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)

        if repository.get_user_by_username(con, username):
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

        user = repository.create_user(con, username, hash_password(password), role)
        print(
            f"Success! Created user '{user.username}' (ID: {user.id}) with role '{user.role.value}'."
        )
    finally:
        con.close()


if __name__ == "__main__":
    try:
        prompt_and_create_user()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)
