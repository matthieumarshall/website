"""
CLI script to seed the rules-and-constitution static page from the league handbook.

Converts docs/OXL_League_Manual.md to HTML and upserts it into the database.
After seeding, the content is editable via the admin UI at /rules-and-constitution/edit.

Usage:
    python -m cli.seed_rules [--md-path <path>]

Options:
    --md-path    Path to the Markdown file (default: docs/OXL_League_Manual.md)

Example:
    python -m cli.seed_rules
    python -m cli.seed_rules --md-path docs/OXL_League_Manual.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("markdown is required. Run: uv add --optional dev markdown")

import duckdb

from website import repository
from website.database import _get_db_path, run_migrations

_DEFAULT_MD_PATH = Path("docs") / "OXL_League_Manual.md"
_SLUG = "rules-and-constitution"


def _build_html(md_path: Path) -> str:
    """Convert the Markdown file to HTML, adding Bootstrap table classes."""
    content = md_path.read_text(encoding="utf-8")
    html = markdown.markdown(
        content,
        extensions=["tables", "sane_lists"],
    )
    # Add Bootstrap classes so tables render consistently with the rest of the site
    html = html.replace("<table>", '<table class="table table-bordered table-sm">')
    return html


def _seed_rules(con: duckdb.DuckDBPyConnection, md_path: Path) -> str:
    """Build HTML from md_path and upsert the rules static page.

    Returns the generated HTML string.
    Raises ValueError if the Markdown file does not exist.
    """
    if not md_path.exists():
        raise ValueError(f"Markdown file not found at {md_path}")
    html = _build_html(md_path)
    repository.upsert_static_page(con, _SLUG, html)
    return html


def seed_rules(md_path: Path) -> None:
    db_path = _get_db_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    try:
        run_migrations(con)
        print(f"Converting {md_path} to HTML ...")
        try:
            html = _seed_rules(con, md_path)
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        print(f"  Generated {len(html):,} characters of HTML")
        print(f"  Seeded slug='{_SLUG}'")
        print("Done. Visit /rules-and-constitution to review the content.")
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed the rules-and-constitution page from the league handbook."
    )
    parser.add_argument(
        "--md-path",
        type=Path,
        default=_DEFAULT_MD_PATH,
        help=f"Path to Markdown source (default: {_DEFAULT_MD_PATH})",
    )
    args = parser.parse_args()
    seed_rules(args.md_path)
