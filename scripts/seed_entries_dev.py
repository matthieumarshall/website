"""Dev seed script: populate the local DuckDB with test data for team entries.

Creates:
- Season "2025-26" with entry config (entries open, EA ref date 2025-08-31)
- 5 future fixtures
- Price tiers: fixtures_remaining 5→4→3→2→1 with decreasing prices
- Admin user: admin / admin123
- Club: Oxford City AC (EA club ID 1765 — staging test club)
- Club manager user: oxc_manager / manager123

Run from repo root:
    uv run python scripts/seed_entries_dev.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure project source is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import duckdb

from website.auth import hash_password
from website.database import run_migrations
from website import repository
from website.models import UserRole


DB_PATH = Path(__file__).parent.parent / "data" / "app.duckdb"


def main() -> None:
    print(f"Connecting to {DB_PATH} ...")
    con = duckdb.connect(str(DB_PATH))
    run_migrations(con)

    # ------------------------------------------------------------------
    # Season
    # ------------------------------------------------------------------
    existing = con.execute("SELECT id FROM seasons WHERE name='2025-26'").fetchone()
    if existing:
        season_id = existing[0]
        print(f"Season '2025-26' already exists (id={season_id})")
    else:
        con.execute("INSERT INTO seasons (name) VALUES ('2025-26')")
        row = con.execute("SELECT id FROM seasons WHERE name='2025-26'").fetchone()
        assert row is not None
        season_id = row[0]
        print(f"Created season '2025-26' (id={season_id})")

    # ------------------------------------------------------------------
    # Fixtures (5 future dates)
    # ------------------------------------------------------------------
    today = date.today()
    fixture_dates = [today + timedelta(weeks=i * 3 + 2) for i in range(5)]
    for i, fixture_date in enumerate(fixture_dates, start=1):
        existing_f = con.execute(
            "SELECT id FROM fixtures WHERE season_id=? AND date=?",
            [season_id, fixture_date],
        ).fetchone()
        if not existing_f:
            con.execute(
                """
                INSERT INTO fixtures (season_id, name, date, location, postcode)
                VALUES (?, ?, ?, 'TBC', 'OX1 1AA')
                """,
                [season_id, f"Race {i}", fixture_date],
            )
            print(f"  Created fixture {i}: {fixture_date}")
        else:
            print(f"  Fixture {i} already exists: {fixture_date}")

    # ------------------------------------------------------------------
    # Season entry config
    # ------------------------------------------------------------------
    repository.upsert_season_entry_config(
        con,
        season_id=season_id,
        entries_open=True,
        ea_reference_date="2025-08-31",
        total_fixtures=5,
    )
    print("Set season entry config (entries_open=True, ref_date=2025-08-31)")

    # ------------------------------------------------------------------
    # Price tiers
    # ------------------------------------------------------------------
    price_tiers = [
        (5, 1500, 800),  # 5 remaining: £15 junior / £8 adult
        (4, 1200, 650),  # 4 remaining: £12 / £6.50
        (3, 900, 500),  # 3 remaining: £9  / £5
        (2, 600, 350),  # 2 remaining: £6  / £3.50
        (1, 300, 200),  # 1 remaining: £3  / £2
    ]
    for fixtures_remaining, junior_pence, adult_pence in price_tiers:
        repository.upsert_price_tier(
            con,
            season_id=season_id,
            fixtures_remaining=fixtures_remaining,
            junior_pence=junior_pence,
            adult_pence=adult_pence,
        )
    print("Created price tiers (5→1 fixtures remaining)")

    # ------------------------------------------------------------------
    # Admin user
    # ------------------------------------------------------------------
    if not repository.get_user_by_username(con, "admin"):
        con.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
            ["admin", hash_password("admin123"), UserRole.admin.value],
        )
        print("Created admin user: admin / admin123")
    else:
        print("Admin user already exists")

    # ------------------------------------------------------------------
    # Club: Oxford City AC
    # ------------------------------------------------------------------
    existing_club = con.execute("SELECT id FROM clubs WHERE oxl_code='OXC'").fetchone()
    if existing_club:
        club_id = existing_club[0]
        print(f"Club 'Oxford City AC' already exists (id={club_id})")
    else:
        repository.create_club(
            con,
            name="Oxford City AC",
            oxl_code="OXC",
            ea_club_id="1765",  # EA staging test club
        )
        row = con.execute("SELECT id FROM clubs WHERE oxl_code='OXC'").fetchone()
        assert row is not None
        club_id = row[0]
        print(f"Created club 'Oxford City AC' (id={club_id})")

    # ------------------------------------------------------------------
    # Club manager user
    # ------------------------------------------------------------------
    existing_manager = repository.get_user_by_username(con, "oxc_manager")
    if not existing_manager:
        con.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
            ["oxc_manager", hash_password("manager123"), UserRole.club_manager.value],
        )
        row = con.execute(
            "SELECT id FROM users WHERE username='oxc_manager'"
        ).fetchone()
        assert row is not None
        manager_user_id = row[0]
        repository.create_club_manager(
            con,
            user_id=manager_user_id,
            club_id=club_id,
            email="oxc@example.com",
        )
        print(
            f"Created club manager: oxc_manager / manager123 (user_id={manager_user_id})"
        )
    else:
        print("Club manager 'oxc_manager' already exists")

    con.close()
    print("\nSeed complete. Start the dev server:")
    print("  uv run uvicorn website.main:app --reload")


if __name__ == "__main__":
    main()
