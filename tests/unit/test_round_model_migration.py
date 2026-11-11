"""Regression coverage for upgrading legacy round timetables."""

from pathlib import Path

import duckdb

from website import repository
from website.db import run_migrations


def test_upgrade_preserves_legacy_timetable_and_round_numbers(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in sorted(Path("migrations").glob("*.sql")):
        if source.name.startswith("0032_"):
            continue
        (migrations / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    db = duckdb.connect(":memory:")
    run_migrations(db, migrations)
    db.execute("INSERT INTO seasons (name) VALUES ('2025')")
    db.execute(
        "INSERT INTO fixtures (season_id, title, date, location_name, address, timetable) VALUES (1, 'Round', '2025-10-01', 'V', 'A', ?)",
        ['[{"event":"Inspection","time":"09:00"},{"event":"Start","time":"10:00"}]'],
    )
    source = Path("migrations/0032_round_schedule_and_manual_results.sql")
    (migrations / source.name).write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    run_migrations(db, migrations)
    fixture = repository.get_fixture_by_id(db, 1)
    assert fixture is not None and fixture.round_number == 1
    assert [(item.event, item.time) for item in fixture.timetable] == [
        ("Inspection", "09:00"),
        ("Start", "10:00"),
    ]
    run_migrations(db, migrations)
    fixture = repository.get_fixture_by_id(db, 1)
    assert fixture is not None
    assert len(fixture.timetable) == 2


def test_previous_local_migration_does_not_duplicate_timetable(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for source in sorted(Path("migrations").glob("*.sql")):
        if source.name.startswith("0032_"):
            continue
        (migrations / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    db = duckdb.connect(":memory:")
    run_migrations(db, migrations)
    db.execute("INSERT INTO seasons (name) VALUES ('2025')")
    db.execute(
        "INSERT INTO fixtures (season_id, title, date, location_name, address, timetable) VALUES (1, 'Round', '2025-10-01', 'V', 'A', ?)",
        ['[{"event":"Start","time":"10:00"}]'],
    )
    source = Path("migrations/0032_round_schedule_and_manual_results.sql")
    sql = source.read_text(encoding="utf-8")
    (migrations / "0031_round_schedule_and_manual_results.sql").write_text(
        sql, encoding="utf-8"
    )
    run_migrations(db, migrations)
    (migrations / source.name).write_text(sql, encoding="utf-8")
    run_migrations(db, migrations)
    fixture = repository.get_fixture_by_id(db, 1)
    assert fixture is not None
    assert [(item.event, item.time) for item in fixture.timetable] == [
        ("Start", "10:00")
    ]
