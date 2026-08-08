"""Shared DB seed data for UI test servers.

Used by tests/ui/conftest.py (pytest-playwright, Python) and
scripts/run_ui_test_server.py (Node @playwright/test webServer) so both test
harnesses exercise the exact same dataset.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from website.auth import hash_password
from website.database import run_migrations
from website.models import AthleteEntryRow, UserRole
from website import repository


@dataclass
class SeededIds:
    """IDs of key seeded rows, for tests that need to reference them directly."""

    season_id: int
    fixture_id: int
    entries_season_id: int
    entry_batch_id: int


def seed_full_dataset(con: duckdb.DuckDBPyConnection) -> SeededIds:
    """Run migrations and seed a full dataset for UI tests.

    Creates: two staff users, a season with two fixtures, individual/team
    standings across many categories, race results, administration sections,
    and a paid entries batch (club + manager + athletes) for receipt tests.
    """
    run_migrations(con)
    repository.create_user(
        con,
        "test_user",
        hash_password("TestPassword123!@#"),
        UserRole.content_creator,
    )
    repository.create_user(
        con,
        "admin_user",
        hash_password("AdminPassword123!@#"),
        UserRole.admin,
    )
    # Seed a season and fixture so fixture-related UI tests have data to work with
    season = repository.create_season(con, "UI Test Season 2026")
    fixture = repository.create_fixture(
        con,
        season_id=season.id,
        title="UI Test Fixture",
        date="2026-06-01",
        location_name="Test Venue",
        address="1 Test Road",
        timetable=[],
        travel_instructions="",
    )
    # Seed individual standings so standings UI tests have data to render
    fid = str(fixture.id)
    con.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                "Senior Women",
                1,
                "Alice Smith",
                "Oxford City AC",
                15,
                1,
                f'{{"{fid}": 1}}',
                False,
            ),
            (
                season.id,
                "Senior Women",
                2,
                "Bob Jones",
                "Abingdon AC",
                28,
                1,
                f'{{"{fid}": 2}}',
                False,
            ),
        ],
    )
    # Seed additional individual categories so the tab row-balancing JS is exercised.
    con.executemany(
        "INSERT INTO individual_standings"
        " (season_id, category, position, athlete_name, club,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                cat,
                1,
                f"Athlete {cat}",
                "Test Club",
                10,
                1,
                f'{{"{fid}": 1}}',
                False,
            )
            for cat in [
                "MV40",
                "MV50",
                "MV60",
                "SM",
                "U11B",
                "U11G",
                "U13B",
                "U13G",
                "U15B",
                "U15G",
            ]
        ],
    )
    # Seed team standings
    con.execute(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            season.id,
            "Senior Women",
            1,
            "Oxford City AC A",
            "Oxford City AC",
            "A",
            10,
            1,
            f'{{"{fid}": 1}}',
            False,
        ),
    )
    # Seed additional team categories so the team tab group also wraps.
    con.executemany(
        "INSERT INTO team_standings"
        " (season_id, category, position, team_name, club, team_label,"
        "  total_score, rounds_competed, fixture_scores, is_imported)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                season.id,
                cat,
                1,
                f"Test {cat} A",
                "Test Club",
                "A",
                10,
                1,
                f'{{"{fid}": 1}}',
                False,
            )
            for cat in [
                "Men's Teams D1",
                "Men's Teams D2",
                "U11B",
                "U11G",
                "U13B",
                "U13G",
                "U15B",
                "Women's Teams D1",
            ]
        ],
    )
    # Seed a race and results so results-browsing UI tests have data to render
    race = repository.create_race(con, fixture.id, "Senior Women Race", display_order=1)
    repository.create_result(
        con,
        race_id=race.id,
        position=1,
        athlete_name="Alice Smith",
        time="35:12",
        category="Senior Women",
        gender="F",
        race_number=101,
        category_position=1,
        gender_position=1,
        club="Oxford City AC",
    )
    repository.create_result(
        con,
        race_id=race.id,
        position=2,
        athlete_name="Bob Jones",
        time="36:45",
        category="Senior Men",
        gender="M",
        race_number=202,
        category_position=1,
        gender_position=1,
        club="Abingdon AC",
    )
    # Seed a second fixture so fixture-tab active-state tests can switch rounds
    fixture2 = repository.create_fixture(
        con,
        season_id=season.id,
        title="UI Test Fixture 2",
        date="2026-07-01",
        location_name="Test Venue 2",
        address="2 Test Road",
        timetable=[],
        travel_instructions="",
    )
    race2 = repository.create_race(
        con, fixture2.id, "Senior Men Race 2", display_order=1
    )
    repository.create_result(
        con,
        race_id=race2.id,
        position=1,
        athlete_name="Charlie Brown",
        time="33:00",
        category="Senior Men",
        gender="M",
        race_number=301,
        category_position=1,
        gender_position=1,
        club="Oxford City AC",
    )
    # Seed administration sections so the administration page has data to render
    for i, (slug, title) in enumerate([("notices", "Notices"), ("agendas", "Agendas")]):
        repository.create_administration_section(
            con, slug=slug, title=title, description="", sort_order=i
        )

    # ------------------------------------------------------------------
    # Seed entries domain: club, manager, config, paid batch for receipt tests
    # Use a dedicated season so we don't hit the max-fixtures-per-season limit.
    # ------------------------------------------------------------------
    entries_season = repository.create_season(con, "Entries Test Season")

    repository.create_club(con, name="UI Test Club", oxl_code="UTC", ea_club_id="9999")
    row = con.execute("SELECT id FROM clubs WHERE oxl_code='UTC'").fetchone()
    assert row is not None
    ui_club_id = row[0]

    # Club manager user
    con.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        [
            "entries_manager",
            hash_password("ManagerPassword123!@#"),
            UserRole.club_manager.value,
        ],
    )
    row = con.execute(
        "SELECT id FROM users WHERE username='entries_manager'"
    ).fetchone()
    assert row is not None
    manager_user_id = row[0]
    repository.create_club_manager(
        con, user_id=manager_user_id, club_id=ui_club_id, email="mgr@example.com"
    )

    # Entry config: open, future fixtures, with per-fixture prices
    repository.upsert_season_entry_config(
        con,
        season_id=entries_season.id,
        entries_open=True,
        ea_reference_date="2025-08-31",
        total_fixtures=5,
        junior_pence_per_fixture=160,  # £1.60/fixture × 5 = £8.00
        adult_pence_per_fixture=200,  # £2.00/fixture × 5 = £10.00
    )

    # Future fixtures (so compute_fixtures_remaining > 0)
    today = date.today()
    for i in range(5):
        future = today + timedelta(weeks=(i + 1) * 3)
        repository.create_fixture(
            con,
            season_id=entries_season.id,
            title=f"UI Race {i + 1}",
            date=str(future),
            location_name="UI Venue",
            address="1 Test Road",
            timetable=[],
            travel_instructions="",
        )

    # Pre-paid entry batch for receipt tests
    ui_batch = repository.create_entry_batch(
        con,
        season_id=entries_season.id,
        club_id=ui_club_id,
        manager_user_id=manager_user_id,
        fixtures_remaining_at_entry=5,
        total_pence=1800,
    )
    repository.create_athlete_entries(
        con,
        batch_id=ui_batch.id,
        season_id=entries_season.id,
        club_id=ui_club_id,
        athletes=[
            AthleteEntryRow(
                ea_urn=10000001,
                athlete_name="Test Junior",
                date_of_birth=date(2012, 3, 15),
                ea_age_category="U15",
                is_junior=True,
                amount_pence=800,
            ),
            AthleteEntryRow(
                ea_urn=10000002,
                athlete_name="Test Senior",
                date_of_birth=date(1988, 7, 20),
                ea_age_category="Senior",
                is_junior=False,
                amount_pence=1000,
            ),
        ],
    )
    repository.update_batch_status(
        con,
        batch_id=ui_batch.id,
        status="paid",
        stripe_payment_method="card",
    )
    repository.assign_race_numbers(ui_batch.id, con)

    return SeededIds(
        season_id=season.id,
        fixture_id=fixture.id,
        entries_season_id=entries_season.id,
        entry_batch_id=ui_batch.id,
    )
