"""Check that the migrated fixture template provides independent databases."""

import shutil
from pathlib import Path

import duckdb


def test_template_copies_isolate_data_sequences_and_transactions(
    migrated_db_template: Path, tmp_path: Path
):
    paths = [tmp_path / "first.duckdb", tmp_path / "second.duckdb"]
    for path in paths:
        shutil.copyfile(migrated_db_template, path)
    first = duckdb.connect(str(paths[0]))
    second = duckdb.connect(str(paths[1]))
    try:
        first.execute("INSERT INTO seasons (name) VALUES ('first')")
        first_id = first.execute(
            "SELECT id FROM seasons WHERE name = 'first'"
        ).fetchall()[0][0]
        first.execute("BEGIN")
        first.execute("INSERT INTO seasons (name) VALUES ('rolled back')")
        first.execute("ROLLBACK")
        assert (
            first.execute(
                "SELECT count(*) FROM seasons WHERE name = 'rolled back'"
            ).fetchall()[0][0]
            == 0
        )
        assert (
            second.execute(
                "SELECT count(*) FROM seasons WHERE name = 'first'"
            ).fetchall()[0][0]
            == 0
        )
        second.execute("INSERT INTO seasons (name) VALUES ('second')")
        assert (
            second.execute("SELECT id FROM seasons WHERE name = 'second'").fetchall()[
                0
            ][0]
            == first_id
        )
    finally:
        first.close()
        second.close()
