"""Tests for England Athletics API integration in entries.py."""

import os
from datetime import date

import pytest

from website import entries


def _ea_staging_configured() -> bool:
    return bool(
        os.environ.get("EA_STAGING", "").lower() == "true"
        and os.environ.get("EA_CALL_KEY")
        and os.environ.get("EA_CALL_SECRET")
        and os.environ.get("EA_CERT_PATH")
        and os.environ.get("EA_CERT_PASSWORD")
        and os.path.exists(os.environ.get("EA_CERT_PATH", ""))
    )


class TestEAStaging:
    """Integration tests for England Athletics staging API."""

    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason="Requires EA staging mode, credentials, and a valid certificate path",
    )
    def test_fetch_club_athletes_returns_list(self):
        """Test that fetch_club_athletes returns a list of athletes from staging."""
        # Using staging test club ID (OXL uses 1765 for zzz Runners in staging)
        athletes = entries.fetch_club_athletes("1765")

        assert isinstance(athletes, list)
        assert len(athletes) > 0, "Expected at least one athlete from staging club"

    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason="Requires EA staging mode, credentials, and a valid certificate path",
    )
    def test_fetch_club_athletes_response_schema(self):
        """Test that athlete responses have required fields."""
        athletes = entries.fetch_club_athletes("1765")

        assert len(athletes) > 0
        athlete = athletes[0]

        # Verify required fields
        assert "IndividualRef" in athlete, "Missing IndividualRef"
        assert "FirstName" in athlete, "Missing FirstName"
        assert "LastName" in athlete, "Missing LastName"
        assert "DateOfBirth" in athlete, "Missing DateOfBirth"
        assert "RegistrationStatus" in athlete, "Missing RegistrationStatus"

        # Verify types
        assert isinstance(athlete["IndividualRef"], (int, str))
        assert isinstance(athlete["FirstName"], str)
        assert isinstance(athlete["LastName"], str)
        assert isinstance(athlete["RegistrationStatus"], str)

    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason="Requires EA staging mode, credentials, and a valid certificate path",
    )
    def test_registration_status_normalization(self):
        """Test that registration status is properly normalized."""
        athletes = entries.fetch_club_athletes("1765")

        statuses = {a["RegistrationStatus"] for a in athletes}
        # Should only contain normalized values
        valid_statuses = {"Registered", "Not Registered"}
        assert statuses.issubset(valid_statuses), (
            f"Invalid statuses found: {statuses - valid_statuses}"
        )

    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason="Requires EA staging mode, credentials, and a valid certificate path",
    )
    def test_age_category_calculation(self):
        """Test that age category calculation works for returned athletes."""
        athletes = entries.fetch_club_athletes("1765")
        reference_date = date(2025, 8, 31)  # Standard EA reference date

        assert len(athletes) > 0
        for athlete in athletes[:5]:  # Test first 5
            dob_str = athlete.get("DateOfBirth", "")
            if dob_str:
                try:
                    dob = date.fromisoformat(dob_str[:10])
                    category = entries.get_oxl_age_category(dob, reference_date)
                    assert category in {
                        "U9",
                        "U11",
                        "U13",
                        "U15",
                        "U17",
                        "U20",
                        "Senior",
                        "Veteran",
                    }, f"Invalid category {category}"
                    is_junior = entries.is_junior(category)
                    assert isinstance(is_junior, bool)
                except ValueError:
                    pass  # Skip if DOB is malformed


class TestEATestMode:
    """Tests for EA test mode (dummy data fallback)."""

    def test_test_mode_returns_dummy_athletes(self):
        """Test that EA_TEST_MODE returns realistic dummy athletes."""
        # Temporarily enable test mode
        original = os.environ.get("EA_TEST_MODE")
        try:
            os.environ["EA_TEST_MODE"] = "true"
            athletes = entries.fetch_club_athletes("9999")  # Dummy club ID

            assert isinstance(athletes, list)
            assert len(athletes) == 8, "Expected 8 test athletes"

            # Verify structure
            for athlete in athletes:
                assert "IndividualRef" in athlete
                assert "FirstName" in athlete
                assert "LastName" in athlete
                assert "DateOfBirth" in athlete
                assert "RegistrationStatus" in athlete
        finally:
            if original is None:
                os.environ.pop("EA_TEST_MODE", None)
            else:
                os.environ["EA_TEST_MODE"] = original

    def test_age_categories_for_test_athletes(self):
        """Test age category logic against test athlete DOBs."""
        reference_date = date(2025, 8, 31)

        test_cases = [
            ("2010-05-15", "U17"),  # Alice (age 15)
            ("2012-08-22", "U15"),  # Bob (age 13)
            ("2008-03-10", "U20"),  # Charlie (age 17)
            ("2015-11-30", "U11"),  # Diana (age 9)
            ("1995-07-05", "Senior"),  # Edward (age 30)
        ]

        for dob_str, expected_category in test_cases:
            dob = date.fromisoformat(dob_str)
            category = entries.get_oxl_age_category(dob, reference_date)
            assert category == expected_category, (
                f"DOB {dob_str}: expected {expected_category}, got {category}"
            )
