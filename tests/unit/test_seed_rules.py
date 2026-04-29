import duckdb
import pytest

from website import repository
from website.database import run_migrations
from cli.seed_rules import _seed_rules, _SLUG


@pytest.fixture()
def db() -> duckdb.DuckDBPyConnection:  # type: ignore[misc]  # ty:ignore[invalid-return-type]
    con = duckdb.connect(":memory:")
    run_migrations(con)
    yield con
    con.close()


class TestSeedRules:
    def test_converts_markdown_and_upserts(
        self, db: duckdb.DuckDBPyConnection, tmp_path: pytest.TempPathFactory
    ) -> None:
        md_file = tmp_path / "rules.md"  # type: ignore[operator]  # ty:ignore[unsupported-operator]
        md_file.write_text("# Rules\n\nSome rules here.\n", encoding="utf-8")
        html = _seed_rules(db, md_file)
        assert "<h1>Rules</h1>" in html
        page = repository.get_static_page(db, _SLUG)
        assert page is not None
        assert page.content == html

    def test_raises_when_markdown_file_not_found(
        self, db: duckdb.DuckDBPyConnection, tmp_path: pytest.TempPathFactory
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            _seed_rules(db, tmp_path / "missing.md")  # type: ignore[operator]  # ty:ignore[unsupported-operator]

    def test_upsert_overwrites_existing_content(
        self, db: duckdb.DuckDBPyConnection, tmp_path: pytest.TempPathFactory
    ) -> None:
        md_file = tmp_path / "rules.md"  # type: ignore[operator]  # ty:ignore[unsupported-operator]
        md_file.write_text("# Version 1\n", encoding="utf-8")
        _seed_rules(db, md_file)

        md_file.write_text("# Version 2\n", encoding="utf-8")
        html = _seed_rules(db, md_file)

        page = repository.get_static_page(db, _SLUG)
        assert page is not None
        assert "Version 2" in page.content
        assert "Version 1" not in page.content
        assert page.content == html

    def test_adds_bootstrap_table_classes(
        self, db: duckdb.DuckDBPyConnection, tmp_path: pytest.TempPathFactory
    ) -> None:
        md_file = tmp_path / "rules.md"  # type: ignore[operator]  # ty:ignore[unsupported-operator]
        md_file.write_text(
            "| Col1 | Col2 |\n|------|------|\n| A | B |\n", encoding="utf-8"
        )
        html = _seed_rules(db, md_file)
        assert 'class="table table-bordered table-sm"' in html
