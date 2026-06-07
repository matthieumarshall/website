"""Unit tests for website.entries — age category, eligibility, fixtures remaining."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import duckdb

from website.entries import (
    compute_fixtures_remaining,
    get_oxl_age_category,
    is_entry_open_for_fixture,
    is_junior,
)

# ---------------------------------------------------------------------------
# get_oxl_age_category
# ---------------------------------------------------------------------------


class TestGetOxlAgeCategory:
    """Boundary tests for every age-category transition."""

    REF = date(2025, 8, 31)  # typical UK Athletics reference date

    def test_u9_boundary_exactly_8(self):
        # 8 years old on ref date → U9
        dob = date(2017, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U9"

    def test_u11_boundary_exactly_9(self):
        dob = date(2016, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U11"

    def test_u11_boundary_exactly_10(self):
        dob = date(2015, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U11"

    def test_u13_boundary_exactly_11(self):
        dob = date(2014, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U13"

    def test_u13_boundary_exactly_12(self):
        dob = date(2013, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U13"

    def test_u15_boundary_exactly_13(self):
        dob = date(2012, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U15"

    def test_u15_boundary_exactly_14(self):
        dob = date(2011, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U15"

    def test_u17_boundary_exactly_15(self):
        dob = date(2010, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U17"

    def test_u17_boundary_exactly_16(self):
        dob = date(2009, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U17"

    def test_u20_boundary_exactly_17(self):
        dob = date(2008, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U20"

    def test_u20_boundary_exactly_19(self):
        dob = date(2006, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "U20"

    def test_senior_boundary_exactly_20(self):
        dob = date(2005, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "Senior"

    def test_senior_boundary_exactly_34(self):
        dob = date(1991, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "Senior"

    def test_veteran_boundary_exactly_35(self):
        dob = date(1990, 8, 31)
        assert get_oxl_age_category(dob, self.REF) == "Veteran"

    def test_veteran_very_old(self):
        dob = date(1950, 1, 1)
        assert get_oxl_age_category(dob, self.REF) == "Veteran"

    def test_birthday_not_yet_reached_on_ref_date(self):
        # DOB is 1 Sep 2015; on 31 Aug 2025 they have not yet turned 10
        dob = date(2015, 9, 1)
        assert (
            get_oxl_age_category(dob, self.REF) == "U11"
        )  # still 9 → U11? no: 9 → U9 is ≤8. wait…
        # age = 2025 - 2015 - (True because (8,31) < (9,1)) = 10 - 1 = 9 → U11
        assert get_oxl_age_category(dob, self.REF) == "U11"


# ---------------------------------------------------------------------------
# is_junior
# ---------------------------------------------------------------------------


class TestIsJunior:
    def test_u9_is_junior(self):
        assert is_junior("U9") is True

    def test_u11_is_junior(self):
        assert is_junior("U11") is True

    def test_u13_is_junior(self):
        assert is_junior("U13") is True

    def test_u15_is_junior(self):
        assert is_junior("U15") is True

    def test_u17_is_junior(self):
        assert is_junior("U17") is True

    def test_u20_is_not_junior(self):
        assert is_junior("U20") is False

    def test_senior_is_not_junior(self):
        assert is_junior("Senior") is False

    def test_veteran_is_not_junior(self):
        assert is_junior("Veteran") is False


# ---------------------------------------------------------------------------
# is_entry_open_for_fixture
# ---------------------------------------------------------------------------


class TestIsEntryOpenForFixture:
    def test_open_when_fixture_is_in_future(self):
        # A fixture date well in the future → entry is open
        future_date = date(2099, 1, 1)
        assert is_entry_open_for_fixture(future_date) is True

    def test_closed_when_fixture_is_in_past(self):
        # A fixture date well in the past → entry is closed
        past_date = date(2000, 1, 1)
        assert is_entry_open_for_fixture(past_date) is False

    def test_open_before_midday_utc_on_fixture_day(self):
        # Pin now to 11:59 UTC on fixture day
        fixture_date = date(2025, 6, 15)
        mock_now = datetime(2025, 6, 15, 11, 59, tzinfo=timezone.utc)
        with patch("website.entries.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine.side_effect = datetime.combine
            assert is_entry_open_for_fixture(fixture_date) is True

    def test_closed_at_midday_utc_on_fixture_day(self):
        # Pin now to exactly 12:00 UTC on fixture day (deadline reached)
        fixture_date = date(2025, 6, 15)
        mock_now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
        with patch("website.entries.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.combine.side_effect = datetime.combine
            assert is_entry_open_for_fixture(fixture_date) is False


# ---------------------------------------------------------------------------
# compute_fixtures_remaining
# ---------------------------------------------------------------------------


class TestComputeFixturesRemaining:
    def _make_db(self, fixture_dates: list[date]) -> duckdb.DuckDBPyConnection:
        """Create an in-memory DuckDB with a fixtures table for testing."""
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE fixtures (id INTEGER, season_id INTEGER, date DATE)")
        for i, d in enumerate(fixture_dates):
            con.execute(
                "INSERT INTO fixtures VALUES (?, ?, ?)",
                [i + 1, 1, d],
            )
        return con

    def test_counts_only_future_fixtures(self):
        past = date(2000, 1, 1)
        future = date(2099, 1, 1)
        db = self._make_db([past, future, future])
        assert compute_fixtures_remaining(1, db) == 2

    def test_zero_when_all_past(self):
        db = self._make_db([date(2000, 1, 1), date(2001, 1, 1)])
        assert compute_fixtures_remaining(1, db) == 0

    def test_all_future(self):
        db = self._make_db([date(2099, 1, 1), date(2099, 2, 1), date(2099, 3, 1)])
        assert compute_fixtures_remaining(1, db) == 3

    def test_empty_season(self):
        db = self._make_db([])
        assert compute_fixtures_remaining(1, db) == 0


# ---------------------------------------------------------------------------
# T050: Second batch excludes already-entered athletes (repository level)
# ---------------------------------------------------------------------------


class TestGetEnteredEaUrns:
    """Verify that get_entered_ea_urns correctly excludes already-entered athletes."""

    def _make_db_with_entry(self) -> duckdb.DuckDBPyConnection:
        """Return a minimal in-memory DB with one athlete_entries row."""
        from website.database import run_migrations

        con = duckdb.connect(":memory:")
        run_migrations(con)
        # Insert minimal supporting records
        con.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES ('u1', 'x', 'club_manager')"
        )
        con.execute("INSERT INTO seasons (name) VALUES ('2025-26')")
        con.execute(
            "INSERT INTO clubs (name, oxl_code, ea_club_id) VALUES ('Oxford City AC', 'OXC', '1')"
        )
        con.execute("INSERT INTO club_managers (user_id, club_id) VALUES (1, 1)")
        con.execute(
            """
            INSERT INTO entry_batches
              (season_id, club_id, manager_user_id, status,
               fixtures_remaining_at_entry, total_pence)
            VALUES (1, 1, 1, 'paid', 3, 500)
            """
        )
        con.execute(
            """
            INSERT INTO athlete_entries
              (batch_id, season_id, club_id, ea_urn,
               athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence)
            VALUES (1, 1, 1, 99887766, 'Bob Smith', '1985-03-10', 'Senior', false, 500)
            """
        )
        return con

    def test_returns_urn_of_entered_athlete(self):
        from website import repository

        con = self._make_db_with_entry()
        urns = repository.get_entered_ea_urns(season_id=1, club_id=1, db=con)
        assert 99887766 in urns

    def test_different_club_not_excluded(self):
        from website import repository

        con = self._make_db_with_entry()
        # Club 2 has no entries → empty set
        urns = repository.get_entered_ea_urns(season_id=1, club_id=2, db=con)
        assert 99887766 not in urns

    def test_different_season_not_excluded(self):
        from website import repository

        con = self._make_db_with_entry()
        # Season 2 doesn't exist → empty set
        urns = repository.get_entered_ea_urns(season_id=2, club_id=1, db=con)
        assert urns == set()
