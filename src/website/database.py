import os
from pathlib import Path
from typing import Generator

import duckdb
from fastapi import Request

_DATA_DIR = Path("data")
_DB_PATH = _DATA_DIR / "app.duckdb"
_MIGRATIONS_DIR = Path("migrations")


def _get_db_path() -> str:
    return os.environ.get("DATABASE_URL", str(_DB_PATH))


def run_migrations(con: duckdb.DuckDBPyConnection) -> None:
    """Apply any unapplied SQL migrations from the migrations/ directory in order."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename  VARCHAR PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    if not _MIGRATIONS_DIR.exists():
        return

    applied = {
        row[0] for row in con.execute("SELECT filename FROM _migrations").fetchall()
    }

    for migration_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if migration_file.name not in applied:
            con.execute(migration_file.read_text(encoding="utf-8"))
            con.execute(
                "INSERT INTO _migrations (filename) VALUES (?)",
                [migration_file.name],
            )


def get_db(request: Request) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Yield a per-request DuckDB cursor from the application's shared connection.

    Using a cursor() avoids opening a second OS-level file lock per request,
    which would cause 'file being used by another process' errors on Windows.
    """
    cursor = request.app.state.db.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
