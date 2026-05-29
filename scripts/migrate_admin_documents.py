"""
migrate_admin_documents.py
==========================
One-time migration script that:
  1. Applies the database migration (0012) if not already present.
  2. Seeds the four initial sections: notices, agendas, meeting-notes, accounts.
  3. Copies PDF/ZIP files from data/original_website/files/admin/ into
     data/uploads/administration/<section_slug>/ with UUID-prefixed filenames.
  4. Inserts a row into administration_documents for each copied file with
     a human-readable display_name derived from the original filename.

Run from the project root:
    uv run python scripts/migrate_admin_documents.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import uuid
from pathlib import Path

# Ensure UTF-8 output on Windows terminals that default to cp1252
import io as _io

if isinstance(sys.stdout, _io.TextIOWrapper) and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Allow importing from src/website
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DB_PATH = Path("data/app.duckdb")
_SOURCE_ROOT = Path("data/original_website/files/admin")
_DEST_ROOT = Path("data/uploads/administration")

# Map source subdirectory → (section_slug, section_title, section_description)
_SECTION_MAP: dict[str, tuple[str, str, str]] = {
    "notices": (
        "notices",
        "Notices",
        "AGM document packs and official communications.",
    ),
    "agendas": (
        "agendas",
        "Agendas",
        "Meeting agendas published ahead of committee sessions.",
    ),
    "minutes": (
        "meeting-notes",
        "Meeting notes",
        "Approved notes and supporting meeting documents.",
    ),
    "accounts": (
        "accounts",
        "Accounts",
        "Annual accounts and published financial summaries.",
    ),
}

# Sort order within each section: higher = shown first (newer)
_SECTION_SORT_ORDER = {
    "notices": 0,
    "agendas": 1,
    "meeting-notes": 2,
    "accounts": 3,
}

_ALLOWED_EXTENSIONS = {".pdf", ".zip", ".docx", ".xlsx"}


# ---------------------------------------------------------------------------
# Display-name derivation
# ---------------------------------------------------------------------------

# Tokens to strip (revision codes, OXL label, common suffixes)
_STRIP_TOKENS = re.compile(
    r"""
    _?OXL_?          |   # organisation prefix
    _R\d+\b          |   # _R01, _R02, …
    _Rev\d+\b        |   # _Rev1, _Rev2, …
    _D\d+\b          |   # _D01, D02 (draft)
    \bOXL\b\s*       |   # standalone OXL
    \.pdf$           |   # extension (handled separately)
    \.zip$           |
    \.docx$          |
    \.xlsx$
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Abbreviation expansions (applied after other cleanup)
_EXPAND = {
    "AGM": "AGM",  # keep as-is
    "EGM": "EGM",
    "EGRD": "EGRD",
    "WPM": "Working Party Meeting",
    "Docs": "Documents",
    "Mins": "Minutes",
}


def _split_camel(s: str) -> str:
    """Insert a space before each capital letter following a lowercase letter."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def _derive_display_name(stem: str) -> str:
    """Convert a raw filename stem to a human-readable display name.

    Examples:
        2024_25_OXL_Accounts_R02  →  "2024-25 Accounts"
        2025_OXL_AGM_Agenda       →  "2025 AGM Agenda"
        20190911_OXL_EGRD_ReviewMeetingMinutes  →  "2019-09-11 EGRD Review Meeting Minutes"
        OXL 2024-25 AGM Documentation  →  "2024-25 AGM Documentation"
        EGRD-ReviewMeetingDocs-D01  →  "EGRD Review Meeting Docs"
    """
    name = stem

    # Handle "OXL YYYY-YY ..." style (spaces already present)
    name = re.sub(r"^OXL\s+", "", name, flags=re.IGNORECASE)

    # Convert YYYYMMDD prefix to YYYY-MM-DD
    name = re.sub(r"^(\d{4})(\d{2})(\d{2})_", r"\1-\2-\3 ", name)

    # Convert YYYY_YY (season) to YYYY-YY
    name = re.sub(r"^(\d{4})_(\d{2})_", r"\1-\2 ", name)

    # Strip OXL prefix and revision codes
    name = _STRIP_TOKENS.sub(" ", name)

    # Split CamelCase words before replacing separators
    name = _split_camel(name)

    # Replace underscores and hyphens with spaces and collapse whitespace.
    # Only replace hyphens that are NOT between two digits (preserves "2023-24").
    name = name.replace("_", " ").replace("&", " and ")
    name = re.sub(r"(?<!\d)-(?!\d)", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()

    # Title-case each word while preserving known acronyms
    words = name.split()
    result: list[str] = []
    for w in words:
        upper = w.upper()
        if upper in _EXPAND:
            result.append(_EXPAND[upper])
        elif w.isupper() and len(w) <= 5:
            result.append(w)  # keep acronyms like AGM, EGM
        else:
            result.append(w.capitalize())
    return " ".join(result)


# ---------------------------------------------------------------------------
# Sort order extraction
# ---------------------------------------------------------------------------


def _sort_order_from_name(stem: str) -> int:
    """Extract a sort key from the filename. Higher = shown first (newer)."""
    # YYYYMMDD prefix
    m = re.match(r"^(\d{8})", stem)
    if m:
        return int(m.group(1))
    # YYYY_YY season accounts e.g. 2024_25
    m = re.match(r"^(\d{4})_(\d{2})", stem)
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    # OXL YYYY-YY style (spaces)
    m = re.search(r"(\d{4})-(\d{2})", stem)
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    # Plain YYYY
    m = re.match(r"^(\d{4})", stem)
    if m:
        return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


def _connect() -> duckdb.DuckDBPyConnection:
    if not _DB_PATH.exists():
        print(f"[ERROR] Database not found at {_DB_PATH}. Run migrations first.")
        sys.exit(1)
    return duckdb.connect(str(_DB_PATH))


def _ensure_section(
    db: duckdb.DuckDBPyConnection,
    slug: str,
    title: str,
    description: str,
    sort_order: int,
    dry_run: bool,
) -> int | None:
    """Create section if it doesn't exist. Returns the section ID."""
    row = db.execute(
        "SELECT id FROM administration_sections WHERE slug = ?", [slug]
    ).fetchone()
    if row:
        section_id: int = row[0]
        print(f"  [section] '{slug}' already exists (id={section_id})")
        return section_id
    if dry_run:
        print(f"  [DRY-RUN] Would create section slug='{slug}' title='{title}'")
        return None
    db.execute(
        "INSERT INTO administration_sections (slug, title, description, sort_order)"
        " VALUES (?, ?, ?, ?)",
        [slug, title, description, sort_order],
    )
    row = db.execute(
        "SELECT id FROM administration_sections WHERE slug = ?", [slug]
    ).fetchone()
    assert row is not None  # noqa: S101
    section_id = row[0]
    print(f"  [section] Created '{slug}' (id={section_id})")
    return section_id


def _file_already_seeded(
    db: duckdb.DuckDBPyConnection, section_id: int, display_name: str
) -> bool:
    row = db.execute(
        "SELECT id FROM administration_documents"
        " WHERE section_id = ? AND display_name = ?",
        [section_id, display_name],
    ).fetchone()
    return row is not None


def migrate(dry_run: bool = False) -> None:
    db = _connect()

    # Check tables exist
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    if (
        "administration_sections" not in tables
        or "administration_documents" not in tables
    ):
        print(
            "[ERROR] administration_sections / administration_documents tables not found.\n"
            "Apply migrations first:\n"
            "  uv run python scripts/_apply_migrations.py"
        )
        db.close()
        sys.exit(1)

    total_copied = 0
    total_skipped = 0

    for source_dir_name, (slug, title, description) in _SECTION_MAP.items():
        source_dir = _SOURCE_ROOT / source_dir_name
        if not source_dir.is_dir():
            print(f"[WARN] Source directory not found: {source_dir} — skipping")
            continue

        print(f"\n=== {title} ({source_dir_name} -> {slug}) ===")
        sort_order_global = _SECTION_SORT_ORDER.get(slug, 99)
        section_id = _ensure_section(
            db, slug, title, description, sort_order_global, dry_run
        )

        dest_dir = _DEST_ROOT / slug
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(
            (
                f
                for f in source_dir.iterdir()
                if f.suffix.lower() in _ALLOWED_EXTENSIONS
            ),
            key=lambda f: _sort_order_from_name(f.stem),
        )

        # Deduplicate: when multiple files map to the same display_name (different
        # revisions of the same document), keep only the last one in sort order
        # (highest revision suffix) so only the current version is published.
        seen_display_names: dict[str, Path] = {}
        for src_file in files:
            display_name = _derive_display_name(src_file.stem)
            seen_display_names[display_name] = src_file  # later revision overwrites
        deduped_files = sorted(
            seen_display_names.items(), key=lambda kv: _sort_order_from_name(kv[1].stem)
        )

        for display_name, src_file in deduped_files:
            sort_order = _sort_order_from_name(src_file.stem)
            suffix = src_file.suffix.lower()
            file_type = suffix.lstrip(".").upper()

            if section_id is not None and _file_already_seeded(
                db, section_id, display_name
            ):
                print(f"  [SKIP] '{display_name}' already in DB")
                total_skipped += 1
                continue

            safe_filename = f"{uuid.uuid4().hex}{suffix}"
            dest_path = dest_dir / safe_filename

            if dry_run:
                print(
                    f"  [DRY-RUN] {src_file.name}"
                    f"\n             → display_name='{display_name}'"
                    f"\n             → sort_order={sort_order}"
                    f"\n             → dest={dest_path}"
                )
                total_copied += 1
                continue

            shutil.copy2(src_file, dest_path)
            db.execute(
                "INSERT INTO administration_documents"
                " (section_id, display_name, filename, file_type, sort_order)"
                " VALUES (?, ?, ?, ?, ?)",
                [section_id, display_name, safe_filename, file_type, sort_order],
            )
            print(f"  [OK] '{display_name}' → {safe_filename}")
            total_copied += 1

    db.close()
    action = "Would copy" if dry_run else "Copied"
    print(f"\nDone. {action} {total_copied} file(s), skipped {total_skipped}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate old admin documents to the new DB-backed store."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making any changes.",
    )
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
