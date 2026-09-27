"""DuckDB connection management and SQL migrations (framework-independent)."""

import os
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = Path("data") / "app.duckdb"
DEFAULT_MIGRATIONS_DIR = Path("migrations")

Connection = duckdb.DuckDBPyConnection


def get_db_path() -> str:
    """Return the database path from ``DATABASE_URL`` or the default location."""
    return os.environ.get("DATABASE_URL", str(DEFAULT_DB_PATH))


def connect(db_path: str) -> Connection:
    """Open a DuckDB connection, creating the parent directory when needed."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(db_path)


def run_migrations(
    con: Connection, migrations_dir: Path = DEFAULT_MIGRATIONS_DIR
) -> None:
    """Apply any unapplied SQL migrations from *migrations_dir* in order."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename  VARCHAR PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    if not migrations_dir.exists():
        return

    applied = {
        row[0] for row in con.execute("SELECT filename FROM _migrations").fetchall()
    }

    for migration_file in sorted(migrations_dir.glob("*.sql")):
        if migration_file.name not in applied:
            con.execute(migration_file.read_text(encoding="utf-8"))
            con.execute(
                "INSERT INTO _migrations (filename) VALUES (?)",
                [migration_file.name],
            )
