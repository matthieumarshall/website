"""
upload_legacy_admin_content.py
================================
One-off migration script that logs in as an admin user and, via the site's
existing HTTP endpoints (not direct DB writes), uploads legacy content from
``data/original_website/`` that isn't already covered by
``scripts/migrate_admin_documents.py`` / ``migrate_results.py`` /
``migrate_standings.py``:

  * New Administration sections + documents for:
      - Course Maps                        (files/courses/<venue>/*.pdf|docx|csv|...)
      - Venue Maps                         (files/maps/*.pdf)
      - Membership Fees                    (files/memfees/**)
      - Oxfordshire Championships Archive  (files/occchamps/archives/**)
      - Race Numbers                       (files/racenos/**)
      - Timing Information                 (files/tminfo/**)
  * Venue photo/map images (files/courses/<venue>/*.png|jpg|... and
    files/maps/*.png|jpg|...) attached as fixture images to a manually
    curated "most recent fixture held at this venue" mapping — see
    VENUE_FIXTURE_MAP below. That mapping was derived from a one-off
    production DB audit on 2026-07-29 (dates, not ids, were used to pick the
    most recent fixture per venue name); update it if better matches exist.

Usage — run this ON THE VPS against the local app (never over the public
internet), so admin credentials never cross the network:

    ADMIN_USERNAME=committee-tester uv run python scripts/upload_legacy_admin_content.py --dry-run
    ADMIN_USERNAME=committee-tester uv run python scripts/upload_legacy_admin_content.py

You will be prompted for the admin password via a hidden ``getpass`` prompt.
Never pass the password as a CLI argument (it would leak into shell history
and process listings).

Safe to re-run for documents: sections are looked up by title before
creating, and a document is skipped if one with the same display_name
already exists in that section. Fixture-image uploads are NOT idempotent
(the fixture_images table has no caption to de-duplicate on) — only run the
image-upload step once, or remove duplicates afterwards via the front end.
"""

from __future__ import annotations

import argparse
import getpass
import io as _io
import mimetypes
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

if isinstance(sys.stdout, _io.TextIOWrapper) and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Reuse the display-name helper already used for admin docs.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_admin_documents import _derive_display_name  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SOURCE_ROOT = Path("data/original_website/files")
_ALLOWED_DOC_EXTENSIONS = {".pdf", ".zip", ".docx", ".xlsx", ".csv", ".txt"}
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_DOC_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_BYTES = 5 * 1024 * 1024

# New Administration sections: (slug, title, description, source_dir)
_NEW_SECTIONS: list[tuple[str, str, str, Path]] = [
    (
        "course-maps",
        "Course Maps",
        "Cross-country course maps for league venues.",
        _SOURCE_ROOT / "courses",
    ),
    (
        "venue-maps",
        "Venue Maps",
        "Location and parking maps for league venues.",
        _SOURCE_ROOT / "maps",
    ),
    (
        "membership-fees",
        "Membership Fees",
        "Annual club membership fee information.",
        _SOURCE_ROOT / "memfees",
    ),
    (
        "occ-champs-archive",
        "Oxfordshire Championships Archive",
        "Historical Oxfordshire XC Championships entry documents and results.",
        _SOURCE_ROOT / "occchamps" / "archives",
    ),
    (
        "race-numbers",
        "Race Numbers",
        "Blank race number template.",
        _SOURCE_ROOT / "racenos",
    ),
    (
        "timing-info",
        "Timing Information",
        "Timing guides and templates for race officials.",
        _SOURCE_ROOT / "tminfo",
    ),
]

# Human-readable venue names, keyed by files/courses/<key>/ folder name.
# "oldReference" is intentionally excluded (superseded reference material).
VENUE_DISPLAY_NAMES: dict[str, str] = {
    "adderbury": "Adderbury",
    "ascott": "Ascott under Wychwood",
    "bicester": "Bicester Heritage",
    "carterton": "Carterton (Kilkenny Lane)",
    "cirencester": "Cirencester Park",
    "cornbury": "Cornbury",
    "cotswoldfmpk": "Cotswold Farm Park",
    "culham": "Culham Park",
    "farmoor": "Farmoor",
    "finmere": "Finmere",
    "harcourt": "Harcourt",
    "harwell": "Harwell (RAL)",
    "henley": "Henley Showground",
    "horspath": "Horspath (Shotover)",
    "newbury": "Newbury Showground",
    "swindon": "Swindon (Lawns Park)",
    "wittenham": "Wittenham Clumps",
}

# folder key -> (season_id, fixture_id) for the most recent fixture held at
# that venue, per the 2026-07-29 production DB audit. Venues with no entry
# have no matching fixture and are skipped (logged) for image uploads.
VENUE_FIXTURE_MAP: dict[str, tuple[int, int]] = {
    "adderbury": (32, 148),
    "ascott": (29, 132),
    "bicester": (34, 154),
    "carterton": (31, 142),  # "Kilkenny Lane Country Park"
    "cirencester": (35, 159),
    "cornbury": (1, 1),
    "cotswoldfmpk": (35, 161),
    "culham": (29, 133),
    "farmoor": (30, 140),
    "harwell": (30, 139),
    "henley": (35, 162),
    "horspath": (35, 160),
    "newbury": (35, 158),
    "swindon": (33, 152),
    "wittenham": (25, 117),
}

# files/maps/<filename stem, lowercased> -> venue key, for the flat venue-map
# image files that don't live in a per-venue courses/ subfolder. Filenames
# with no confident venue match are skipped (logged) rather than guessed.
MAPS_FILENAME_VENUE: dict[str, str] = {
    "adderbury": "adderbury",
    "ascott": "ascott",
    "bicester": "bicester",
    "carterton": "carterton",
    "cirencester": "cirencester",
    "cotswoldfarmpark": "cotswoldfmpk",
    "culham": "culham",
    "farmoor": "farmoor",
    "harwell": "harwell",
    "henley": "henley",
    "horspath": "horspath",
    "swindon": "swindon",
    "swindon3": "swindon",
    "witclumps1": "wittenham",
    "witclumps2": "wittenham",
    "witclumps21": "wittenham",
    "wittenham clumps": "wittenham",
    "wittenhamclumps": "wittenham",
}


@dataclass
class Stats:
    docs_uploaded: int = 0
    docs_skipped_existing: int = 0
    docs_skipped_ext: int = 0
    docs_errors: int = 0
    images_uploaded: int = 0
    images_skipped_unmatched: int = 0
    images_skipped_size: int = 0
    images_errors: int = 0
    unmatched_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _new_client() -> httpx.Client:
    """Build the shared client for the script's HTTP session.

    In production the app sets `https_only=True` on the session cookie, so the
    server sends it with the `Secure` attribute. This script deliberately talks
    to the app over plain ``http://127.0.0.1`` (loopback) so admin credentials
    never cross the network — but httpx honours the `Secure` flag just like a
    browser would and refuses to resend such a cookie over a non-HTTPS
    connection. Without a fix, every request after login looks unauthenticated.
    Re-insert the session cookie without the `Secure` flag after every response
    so it actually gets sent on subsequent requests.
    """
    client = httpx.Client(follow_redirects=True, timeout=30.0)

    def _persist_session_cookie_over_http(response: httpx.Response) -> None:
        value = response.cookies.get("session")
        if value is not None:
            client.cookies.set("session", value)

    client.event_hooks["response"] = [_persist_session_cookie_over_http]
    return client


def login(client: httpx.Client, base_url: str, username: str, password: str) -> None:
    resp = client.get(f"{base_url}/login")
    resp.raise_for_status()
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not find CSRF token on the login page.")
    resp = client.post(
        f"{base_url}/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": match.group(1),
        },
    )
    if resp.status_code == 401:
        raise RuntimeError("Login failed — check the admin username/password.")
    resp.raise_for_status()


def fetch_manage_page(client: httpx.Client, base_url: str) -> str:
    resp = client.get(f"{base_url}/administration/manage")
    resp.raise_for_status()
    return resp.text


def get_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not match:
        raise RuntimeError("Could not find CSRF token on an authenticated page.")
    return match.group(1)


def parse_sections(html: str) -> dict[str, int]:
    """Map section title -> section id from the administration_manage.html page."""
    return {
        title: int(section_id)
        for section_id, title in re.findall(
            r'<h2 id="section-(\d+)-heading" class="h6 mb-0">([^<]+)</h2>', html
        )
    }


def existing_document_names(html: str, section_id: int) -> set[str]:
    marker = f'id="section-{section_id}-heading"'
    idx = html.find(marker)
    if idx == -1:
        return set()
    next_idx = html.find('id="section-', idx + len(marker))
    chunk = html[idx : next_idx if next_idx != -1 else len(html)]
    return set(
        re.findall(r'class="fw-semibold text-decoration-none"[^>]*>([^<]+)</a>', chunk)
    )


def ensure_section(
    client: httpx.Client,
    base_url: str,
    csrf_token: str,
    manage_html: str,
    slug: str,
    title: str,
    description: str,
    dry_run: bool,
) -> tuple[int, str]:
    sections = parse_sections(manage_html)
    if title in sections:
        print(f"  [section] '{title}' already exists (id={sections[title]})")
        return sections[title], manage_html
    if dry_run:
        print(f"  [DRY-RUN] would create section '{title}' (slug={slug})")
        return -1, manage_html
    resp = client.post(
        f"{base_url}/administration/manage/sections",
        data={
            "title": title,
            "description": description,
            "slug": slug,
            "csrf_token": csrf_token,
        },
    )
    resp.raise_for_status()
    sections = parse_sections(resp.text)
    if title not in sections:
        raise RuntimeError(f"Section '{title}' not found in response after creation.")
    print(f"  [section] created '{title}' (id={sections[title]})")
    return sections[title], resp.text


def upload_document(
    client: httpx.Client,
    base_url: str,
    csrf_token: str,
    section_id: int,
    filepath: Path,
    display_name: str,
    dry_run: bool,
) -> bool:
    if dry_run:
        print(
            f"    [DRY-RUN] would upload '{filepath}' -> section {section_id} as '{display_name}'"
        )
        return True
    content_type = mimetypes.guess_type(filepath.name)[0] or "application/octet-stream"
    with filepath.open("rb") as fh:
        resp = client.post(
            f"{base_url}/administration/manage/sections/{section_id}/documents",
            data={"display_name": display_name, "csrf_token": csrf_token},
            files={"file": (filepath.name, fh, content_type)},
        )
    if resp.status_code >= 400:
        print(
            f"    [ERROR] upload failed for {filepath}: {resp.status_code} {resp.text[:200]!r}"
        )
        return False
    print(f"    [ok] uploaded '{filepath.name}' as '{display_name}'")
    return True


def upload_fixture_image(
    client: httpx.Client,
    base_url: str,
    csrf_token: str,
    season_id: int,
    fixture_id: int,
    filepath: Path,
    dry_run: bool,
) -> bool:
    if dry_run:
        print(f"    [DRY-RUN] would upload image '{filepath}' -> fixture {fixture_id}")
        return True
    content_type = mimetypes.guess_type(filepath.name)[0] or "application/octet-stream"
    with filepath.open("rb") as fh:
        resp = client.post(
            f"{base_url}/fixtures/seasons/{season_id}/fixtures/{fixture_id}/images",
            data={"csrf_token": csrf_token},
            files={"file": (filepath.name, fh, content_type)},
        )
    if resp.status_code >= 400:
        print(
            f"    [ERROR] image upload failed for {filepath}: {resp.status_code} {resp.text[:200]!r}"
        )
        return False
    print(f"    [ok] uploaded image '{filepath.name}' -> fixture {fixture_id}")
    return True


# ---------------------------------------------------------------------------
# Document migration
# ---------------------------------------------------------------------------


def migrate_documents(
    client: httpx.Client,
    base_url: str,
    csrf_token: str,
    manage_html: str,
    dry_run: bool,
    stats: Stats,
) -> str:
    for slug, title, description, source_dir in _NEW_SECTIONS:
        print(f"\n=== {title} ({source_dir}) ===")
        if not source_dir.exists():
            print("  (source directory not found, skipping)")
            continue
        section_id, manage_html = ensure_section(
            client, base_url, csrf_token, manage_html, slug, title, description, dry_run
        )
        existing = (
            existing_document_names(manage_html, section_id) if not dry_run else set()
        )

        files = sorted(
            p
            for p in source_dir.rglob("*")
            if p.is_file() and "oldreference" not in {part.lower() for part in p.parts}
        )
        for filepath in files:
            suffix = filepath.suffix.lower()
            if suffix not in _ALLOWED_DOC_EXTENSIONS:
                print(
                    f"  [skip] '{filepath}' — unsupported extension for admin documents"
                )
                stats.docs_skipped_ext += 1
                continue
            if filepath.stat().st_size > _MAX_DOC_BYTES:
                print(f"  [skip] '{filepath}' — exceeds 20 MB limit")
                stats.docs_errors += 1
                continue

            venue_key = filepath.parent.name if source_dir.name == "courses" else None
            base_display = _derive_display_name(filepath.stem)
            display_name = (
                f"{VENUE_DISPLAY_NAMES.get(venue_key, venue_key)} — {base_display}"
                if venue_key
                else base_display
            )
            if display_name in existing:
                print(f"  [skip] '{display_name}' already uploaded")
                stats.docs_skipped_existing += 1
                continue
            ok = upload_document(
                client,
                base_url,
                csrf_token,
                section_id,
                filepath,
                display_name,
                dry_run,
            )
            if ok:
                existing.add(display_name)
                stats.docs_uploaded += 1
            else:
                stats.docs_errors += 1
    return manage_html


# ---------------------------------------------------------------------------
# Fixture image migration
# ---------------------------------------------------------------------------


def migrate_venue_images(
    client: httpx.Client,
    base_url: str,
    csrf_token: str,
    dry_run: bool,
    stats: Stats,
) -> None:
    print("\n=== Venue photos/maps -> fixture images ===")

    courses_dir = _SOURCE_ROOT / "courses"
    if courses_dir.exists():
        for venue_dir in sorted(courses_dir.iterdir()):
            if not venue_dir.is_dir() or venue_dir.name.lower() == "oldreference":
                continue
            venue_key = venue_dir.name
            target = VENUE_FIXTURE_MAP.get(venue_key)
            image_files = sorted(
                p
                for p in venue_dir.iterdir()
                if p.suffix.lower() in _ALLOWED_IMAGE_EXTENSIONS
            )
            if not image_files:
                continue
            if target is None:
                print(
                    f"  [unmatched] venue '{venue_key}' has {len(image_files)} image(s) but no fixture match"
                )
                stats.images_skipped_unmatched += len(image_files)
                stats.unmatched_files.extend(str(p) for p in image_files)
                continue
            season_id, fixture_id = target
            for filepath in image_files:
                if filepath.stat().st_size > _MAX_IMAGE_BYTES:
                    print(f"  [skip] '{filepath}' — exceeds 5 MB limit")
                    stats.images_skipped_size += 1
                    continue
                ok = upload_fixture_image(
                    client,
                    base_url,
                    csrf_token,
                    season_id,
                    fixture_id,
                    filepath,
                    dry_run,
                )
                stats.images_uploaded += 1 if ok else 0
                stats.images_errors += 0 if ok else 1

    maps_dir = _SOURCE_ROOT / "maps"
    if maps_dir.exists():
        for filepath in sorted(maps_dir.iterdir()):
            if (
                not filepath.is_file()
                or filepath.suffix.lower() not in _ALLOWED_IMAGE_EXTENSIONS
            ):
                continue
            venue_key = MAPS_FILENAME_VENUE.get(filepath.stem.lower())
            target = VENUE_FIXTURE_MAP.get(venue_key) if venue_key else None
            if target is None:
                print(f"  [unmatched] '{filepath.name}' has no confident venue match")
                stats.images_skipped_unmatched += 1
                stats.unmatched_files.append(str(filepath))
                continue
            season_id, fixture_id = target
            if filepath.stat().st_size > _MAX_IMAGE_BYTES:
                print(f"  [skip] '{filepath}' — exceeds 5 MB limit")
                stats.images_skipped_size += 1
                continue
            ok = upload_fixture_image(
                client, base_url, csrf_token, season_id, fixture_id, filepath, dry_run
            )
            stats.images_uploaded += 1 if ok else 0
            stats.images_errors += 0 if ok else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running app (default: local uvicorn on the VPS).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, no writes."
    )
    parser.add_argument(
        "--skip-documents",
        action="store_true",
        help="Skip the administration-document phase.",
    )
    parser.add_argument(
        "--skip-images", action="store_true", help="Skip the fixture-image phase."
    )
    args = parser.parse_args()

    username = os.environ.get("ADMIN_USERNAME") or input("Admin username: ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")

    stats = Stats()
    with _new_client() as client:
        print(f"Logging in to {args.base_url} as '{username}'...")
        login(client, args.base_url, username, password)
        print("Login OK.")

        manage_html = fetch_manage_page(client, args.base_url)
        csrf_token = get_csrf_token(manage_html)

        if not args.skip_documents:
            manage_html = migrate_documents(
                client, args.base_url, csrf_token, manage_html, args.dry_run, stats
            )
        if not args.skip_images:
            migrate_venue_images(client, args.base_url, csrf_token, args.dry_run, stats)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Documents uploaded:            {stats.docs_uploaded}")
    print(f"Documents skipped (existing):  {stats.docs_skipped_existing}")
    print(f"Documents skipped (extension): {stats.docs_skipped_ext}")
    print(f"Document errors:               {stats.docs_errors}")
    print(f"Images uploaded:               {stats.images_uploaded}")
    print(f"Images skipped (unmatched):    {stats.images_skipped_unmatched}")
    print(f"Images skipped (size):         {stats.images_skipped_size}")
    print(f"Image errors:                  {stats.images_errors}")
    if stats.unmatched_files:
        print("\nFiles needing manual review (no venue/fixture match):")
        for f in stats.unmatched_files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
