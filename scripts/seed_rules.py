"""One-off script to convert OXL_League_Manual.md into HTML and seed the
rules-and-constitution static page in the database.

Run once from the project root:
    uv run python scripts/seed_rules.py

The script writes directly to the live database at data/app.duckdb.
After running, the content is editable via the admin UI at /rules-and-constitution/edit.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
try:
    import markdown
except ImportError:
    sys.exit("markdown is required. Run: uv add --optional dev markdown")

import duckdb

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_MD_PATH = _ROOT / "OXL_League_Manual.md"
_DB_PATH = _ROOT / "data" / "app.duckdb"
_SLUG = "rules-and-constitution"


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not _MD_PATH.exists():
        sys.exit(f"Markdown file not found at {_MD_PATH}")
    if not _DB_PATH.exists():
        sys.exit(
            f"Database not found at {_DB_PATH} — start the server first to apply migrations"
        )

    print(f"Converting {_MD_PATH} to HTML ...")
    html = _build_html(_MD_PATH)
    print(f"  Generated {len(html):,} characters of HTML")

    con = duckdb.connect(str(_DB_PATH))
    try:
        con.execute(
            "INSERT INTO static_pages (slug, content)"
            " VALUES (?, ?)"
            " ON CONFLICT (slug) DO UPDATE"
            " SET content = excluded.content,"
            "     updated_at = now()",
            [_SLUG, html],
        )
    finally:
        con.close()

    print(f"  Seeded slug='{_SLUG}' into {_DB_PATH}")
    print("Done. Visit /rules-and-constitution to review the content.")


if __name__ == "__main__":
    main()
