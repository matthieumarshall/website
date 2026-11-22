"""Minimal database readiness probe."""

from website.db import Connection


def probe(db: Connection) -> None:
    """Verify that the application database can answer a read query."""
    db.execute("SELECT count(*) FROM _migrations").fetchone()
