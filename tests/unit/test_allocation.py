"""Tests for club athlete allocation management."""

import pytest

from website import repository


class TestClubAllocation:
    """Tests for club allocation CRUD and validation."""

    def test_upsert_club_allocation_creates_record(self, test_db):
        """Verify allocation insert works."""
        # Create season and club first (FK requirement)
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason1"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason1'"
        ).fetchone()[0]
        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub1", "TC1", "1001"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub1'"
        ).fetchone()[0]

        repository.upsert_club_allocation(
            test_db, season_id=season_id, club_id=club_id, allocated_slots=50
        )
        allocation = repository.get_club_allocation(
            test_db, season_id=season_id, club_id=club_id
        )
        assert allocation == 50

    def test_upsert_club_allocation_updates_existing(self, test_db):
        """Verify allocation update works."""
        # Create season and club first (FK requirement)
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason2"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason2'"
        ).fetchone()[0]
        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub2", "TC2", "1002"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub2'"
        ).fetchone()[0]

        repository.upsert_club_allocation(
            test_db, season_id=season_id, club_id=club_id, allocated_slots=50
        )
        repository.upsert_club_allocation(
            test_db, season_id=season_id, club_id=club_id, allocated_slots=100
        )
        allocation = repository.get_club_allocation(
            test_db, season_id=season_id, club_id=club_id
        )
        assert allocation == 100

    def test_upsert_club_allocation_rejects_zero(self, test_db):
        """Verify zero allocation is rejected."""
        with pytest.raises(ValueError, match="allocated_slots must be greater than 0"):
            repository.upsert_club_allocation(
                test_db, season_id=1, club_id=1, allocated_slots=0
            )

    def test_upsert_club_allocation_rejects_negative(self, test_db):
        """Verify negative allocation is rejected."""
        with pytest.raises(ValueError, match="allocated_slots must be greater than 0"):
            repository.upsert_club_allocation(
                test_db, season_id=1, club_id=1, allocated_slots=-10
            )

    def test_get_club_allocation_returns_none_if_not_set(self, test_db):
        """Verify None is returned for unset allocation."""
        allocation = repository.get_club_allocation(test_db, season_id=1, club_id=999)
        assert allocation is None

    def test_get_club_athlete_count_counts_only_paid(self, test_db):
        """Verify only paid entries count toward allocation."""
        # Create a season, clubs, and entry batches/athletes
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason3"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason3'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub3", "TC3", "1003"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub3'"
        ).fetchone()[0]

        # Create a user for the entry batches
        test_db.execute(
            "INSERT INTO users(username, hashed_password, role) VALUES(?, ?, ?)",
            ["testuser", "hashedpw", "club_manager"],
        )
        user_id = test_db.execute(
            "SELECT id FROM users WHERE username = 'testuser'"
        ).fetchone()[0]

        # Create a paid batch
        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, fixtures_remaining_at_entry, total_pence) VALUES(?, ?, ?, ?, ?, ?)",
            [season_id, club_id, user_id, "paid", 10, 5000],
        )
        paid_batch = test_db.execute(
            "SELECT id FROM entry_batches WHERE season_id = ? AND status = 'paid'",
            [season_id],
        ).fetchone()
        paid_batch_id = paid_batch[0] if paid_batch else None

        # Create a pending batch
        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, fixtures_remaining_at_entry, total_pence) VALUES(?, ?, ?, ?, ?, ?)",
            [season_id, club_id, user_id, "pending_payment", 10, 5000],
        )
        pending_batch = test_db.execute(
            "SELECT id FROM entry_batches WHERE season_id = ? AND status = 'pending_payment'",
            [season_id],
        ).fetchone()
        pending_batch_id = pending_batch[0] if pending_batch else None

        # Add athletes to both batches
        if paid_batch_id:
            test_db.execute(
                "INSERT INTO athlete_entries(batch_id, season_id, club_id, ea_urn, athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    paid_batch_id,
                    season_id,
                    club_id,
                    1001,
                    "Alice",
                    "2010-05-15",
                    "U17",
                    True,
                    1000,
                ],
            )
        if pending_batch_id:
            test_db.execute(
                "INSERT INTO athlete_entries(batch_id, season_id, club_id, ea_urn, athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    pending_batch_id,
                    season_id,
                    club_id,
                    1002,
                    "Bob",
                    "2012-08-22",
                    "U15",
                    True,
                    1000,
                ],
            )

        # Count should only include paid entries
        count = repository.get_club_athlete_count(test_db, season_id, club_id)
        assert count == 1


class TestRaceNumberManagement:
    """Tests for race number updates."""

    def test_update_athlete_race_number_succeeds(self, test_db):
        """Verify race number update works."""
        # Create season, club, batch, athlete
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason4"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason4'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub4", "TC4", "1004"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub4'"
        ).fetchone()[0]

        # Create a user for the entry batch
        test_db.execute(
            "INSERT INTO users(username, hashed_password, role) VALUES(?, ?, ?)",
            ["testuser2", "hashedpw", "club_manager"],
        )
        user_id = test_db.execute(
            "SELECT id FROM users WHERE username = 'testuser2'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, fixtures_remaining_at_entry, total_pence) VALUES(?, ?, ?, ?, ?, ?)",
            [season_id, club_id, user_id, "paid", 10, 5000],
        )
        batch = test_db.execute(
            "SELECT id FROM entry_batches WHERE season_id = ?", [season_id]
        ).fetchone()
        batch_id = batch[0] if batch else None

        if batch_id:
            test_db.execute(
                "INSERT INTO athlete_entries(batch_id, season_id, club_id, ea_urn, athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence, race_number) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    batch_id,
                    season_id,
                    club_id,
                    1001,
                    "Alice",
                    "2010-05-15",
                    "U17",
                    True,
                    1000,
                    1,
                ],
            )
            athlete = test_db.execute(
                "SELECT id FROM athlete_entries WHERE ea_urn = 1001"
            ).fetchone()
            athlete_id = athlete[0] if athlete else None

            # Update race number
            if athlete_id:
                repository.update_athlete_race_number(test_db, athlete_id, 99)

                # Verify update
                result = test_db.execute(
                    "SELECT race_number FROM athlete_entries WHERE id = ?", [athlete_id]
                ).fetchone()
                assert result[0] == 99

    def test_update_athlete_race_number_rejects_zero(self, test_db):
        """Verify zero race number is rejected."""
        with pytest.raises(ValueError, match="race_number must be greater than 0"):
            repository.update_athlete_race_number(test_db, athlete_id=1, race_number=0)

    def test_update_athlete_race_number_rejects_negative(self, test_db):
        """Verify negative race number is rejected."""
        with pytest.raises(ValueError, match="race_number must be greater than 0"):
            repository.update_athlete_race_number(test_db, athlete_id=1, race_number=-5)


class TestAllocationChecking:
    """Tests for allocation checking logic."""

    def test_check_allocation_passes_within_limit(self, test_db):
        """Verify check passes when within limit."""
        from website import entries

        # Setup
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason5"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason5'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub5", "TC5", "1005"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub5'"
        ).fetchone()[0]

        # Set allocation to 10
        repository.upsert_club_allocation(test_db, season_id, club_id, 10)

        # Check should pass for 5 athletes
        result = entries.check_allocation(season_id, club_id, 5, test_db)
        assert result is True

    def test_check_allocation_fails_at_limit(self, test_db):
        """Verify check fails when at limit."""
        from website import entries

        # Setup
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason6"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason6'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub6", "TC6", "1006"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub6'"
        ).fetchone()[0]

        # Set allocation to 10
        repository.upsert_club_allocation(test_db, season_id, club_id, 10)

        # Check should fail for 11 athletes
        result = entries.check_allocation(season_id, club_id, 11, test_db)
        assert result is False

    def test_check_allocation_fails_above_limit(self, test_db):
        """Verify check fails when above limit."""
        from website import entries

        # Setup
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason7"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason7'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub7", "TC7", "1007"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub7'"
        ).fetchone()[0]

        # Set allocation to 10
        repository.upsert_club_allocation(test_db, season_id, club_id, 10)

        # Check should fail for 20 athletes
        result = entries.check_allocation(season_id, club_id, 20, test_db)
        assert result is False

    def test_check_allocation_fails_if_not_set(self, test_db):
        """Verify check fails if allocation is not set."""
        from website import entries

        # Setup
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason8"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason8'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["TestClub8", "TC8", "1008"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'TestClub8'"
        ).fetchone()[0]

        # Don't set allocation - check should fail
        result = entries.check_allocation(season_id, club_id, 1, test_db)
        assert result is False


class TestAllocationDisplay:
    """Tests for allocation display/listing functions."""

    def test_list_club_allocations_for_season(self, test_db):
        """Verify list returns club allocations with usage."""
        # Create season and clubs
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason9"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason9'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["Club A", "CA", "2001"],
        )
        club_a_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'Club A'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["Club B", "CB", "2002"],
        )
        club_b_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'Club B'"
        ).fetchone()[0]

        # Set allocations
        repository.upsert_club_allocation(test_db, season_id, club_a_id, 30)
        repository.upsert_club_allocation(test_db, season_id, club_b_id, 20)

        # Create entry batches and athletes
        test_db.execute(
            "INSERT INTO users(username, hashed_password, role) VALUES(?, ?, ?)",
            ["mgr1", "hash1", "manager"],
        )
        mgr_id = test_db.execute(
            "SELECT id FROM users WHERE username = 'mgr1'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, "
            "fixtures_remaining_at_entry, total_pence, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, now())",
            [season_id, club_a_id, mgr_id, "paid", 10, 5000],
        )
        batch_id = test_db.execute(
            "SELECT id FROM entry_batches WHERE club_id = ?", [club_a_id]
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO athlete_entries(season_id, club_id, batch_id, ea_urn, "
            "athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                season_id,
                club_a_id,
                batch_id,
                1001,
                "Alice",
                "2010-05-15",
                "U13",
                True,
                2500,
            ],
        )
        test_db.execute(
            "INSERT INTO athlete_entries(season_id, club_id, batch_id, ea_urn, "
            "athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                season_id,
                club_a_id,
                batch_id,
                1002,
                "Bob",
                "2012-08-22",
                "U11",
                True,
                2500,
            ],
        )

        allocations = repository.list_club_allocations_for_season(test_db, season_id)
        assert len(allocations) >= 2
        club_a_alloc = next((a for a in allocations if a["club_id"] == club_a_id), None)
        assert club_a_alloc is not None
        assert club_a_alloc["allocated_slots"] == 30
        assert club_a_alloc["current_used"] == 2
        assert club_a_alloc["remaining"] == 28

    def test_list_paid_athlete_entries_for_season(self, test_db):
        """Verify list returns only paid athlete entries."""
        # Create season and club
        test_db.execute("INSERT INTO seasons(name) VALUES(?)", ["TestSeason10"])
        season_id = test_db.execute(
            "SELECT id FROM seasons WHERE name = 'TestSeason10'"
        ).fetchone()[0]

        test_db.execute(
            "INSERT INTO clubs(name, oxl_code, ea_club_id) VALUES(?, ?, ?)",
            ["Club C", "CC", "2003"],
        )
        club_id = test_db.execute(
            "SELECT id FROM clubs WHERE name = 'Club C'"
        ).fetchone()[0]

        # Create user
        test_db.execute(
            "INSERT INTO users(username, hashed_password, role) VALUES(?, ?, ?)",
            ["mgr2", "hash2", "manager"],
        )
        mgr_id = test_db.execute(
            "SELECT id FROM users WHERE username = 'mgr2'"
        ).fetchone()[0]

        # Create paid batch with athletes
        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, "
            "fixtures_remaining_at_entry, total_pence, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, now())",
            [season_id, club_id, mgr_id, "paid", 10, 5000],
        )
        paid_batch_id = test_db.execute(
            "SELECT id FROM entry_batches WHERE status = 'paid'"
        ).fetchone()[0]

        # Create pending batch with athletes
        test_db.execute(
            "INSERT INTO entry_batches(season_id, club_id, manager_user_id, status, "
            "fixtures_remaining_at_entry, total_pence, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, now())",
            [season_id, club_id, mgr_id, "pending_payment", 10, 5000],
        )
        pending_batch_id = test_db.execute(
            "SELECT id FROM entry_batches WHERE status = 'pending_payment'"
        ).fetchone()[0]

        # Add athletes to both batches
        test_db.execute(
            "INSERT INTO athlete_entries(season_id, club_id, batch_id, ea_urn, "
            "athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence, race_number) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                season_id,
                club_id,
                paid_batch_id,
                2001,
                "Charlie",
                "2008-03-10",
                "U15",
                True,
                2500,
                5,
            ],
        )
        test_db.execute(
            "INSERT INTO athlete_entries(season_id, club_id, batch_id, ea_urn, "
            "athlete_name, date_of_birth, ea_age_category, is_junior, amount_pence) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                season_id,
                club_id,
                pending_batch_id,
                2002,
                "Diana",
                "2010-11-25",
                "U13",
                True,
                2500,
            ],
        )

        athletes = repository.list_paid_athlete_entries_for_season(test_db, season_id)
        # Should only have Charlie (from paid batch)
        assert len(athletes) == 1
        assert athletes[0]["athlete_name"] == "Charlie"
        assert athletes[0]["race_number"] == 5
        assert athletes[0]["ea_urn"] == 2001
