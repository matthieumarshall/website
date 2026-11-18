"""Upgrade a populated database with the known result-name aliases."""

from pathlib import Path

import duckdb

from website.db import run_migrations
from website.services.club_identity import ClubRegistry


def test_upgrade_links_known_aliases_without_changing_existing_rows(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in sorted(Path("migrations").glob("*.sql")):
        if source.name < "0033":
            (migrations / source.name).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
    db = duckdb.connect(":memory:")
    run_migrations(db, migrations)
    db.execute(
        "INSERT INTO clubs (id, name, oxl_code, is_oxfordshire_member) VALUES (991, 'Headington Road Runners', 'HRR', true)"
    )
    source = Path("migrations/0033_club_aliases.sql")
    (migrations / source.name).write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    run_migrations(db, migrations)
    run_migrations(db, migrations)
    club = ClubRegistry.load(db).resolve("Headington RR")
    assert club is not None and club.id == 991
    assert db.execute("SELECT name FROM clubs WHERE id = 991").fetchall() == [
        ("Headington Road Runners",)
    ]
    assert db.execute(
        "SELECT count(*) FROM club_aliases WHERE club_id = 991"
    ).fetchall() == [(1,)]
