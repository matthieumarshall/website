# pyright: reportPrivateUsage=false
"""Tests for England Athletics API integration in entries.py."""

import os
from datetime import date, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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


class TestEAHeaders:
    def test_latin_1_call_secret_is_preserved(self) -> None:
        with patch.dict(
            os.environ,
            {"EA_CALL_KEY": "test_key", "EA_CALL_SECRET": "test_secret\xa3"},
        ):
            headers = getattr(entries, "_ea_headers")()

        secret = next(
            value
            for name, value in headers.raw
            if name.lower() == b"x-trapi-callsecret"
        )
        assert secret == b"test_secret\xa3"

    @pytest.mark.parametrize(
        ("response_status", "expected_http_status"),
        [
            ("InvalidCall", 503),
            ("ApiUserCredentialsIncorrect", 503),
            ("InternalError", 502),
        ],
    )
    def test_unsuccessful_response_status_raises(
        self, response_status: str, expected_http_status: int
    ) -> None:
        validate_response_status = getattr(entries, "_validate_ea_response_status")
        with pytest.raises(HTTPException) as exc_info:
            validate_response_status({"ResponseStatus": response_status})

        assert exc_info.value.status_code == expected_http_status


class TestEAStaging:
    """Unit tests for England Athletics staging API using mocked responses."""

    def test_fetch_club_athletes_returns_list(self):
        """Test that fetch_club_athletes returns a list of athletes from staging."""
        # Mock the httpx.Client and response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ResponseStatus": "SuccessfullyCompleted",
            "Athletes": [
                {
                    "Urn": 12345,
                    "Firstname": "John",
                    "Lastname": "Doe",
                    "Dob": "2010-05-15",
                    "CompetitiveRegStatus": "Active",
                }
            ],
        }

        with (
            patch("website.entries.httpx.Client") as mock_client_class,
            patch.dict(
                os.environ,
                {
                    "EA_STAGING": "true",
                    "EA_CALL_KEY": "test_key",
                    "EA_CALL_SECRET": "test_secret",
                    "EA_CERT_PATH": "/tmp/test.pfx",
                    "EA_CERT_PASSWORD": "test_pass",
                },
            ),
            patch("website.entries.Path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"fake_pfx_data"
            )

            # Mock the certificate extraction
            with patch("website.entries.pkcs12.load_key_and_certificates") as mock_pkcs:
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.backends import default_backend
                from datetime import datetime, timedelta

                # Create mock certificate and key
                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                    backend=default_backend(),
                )
                cert_builder = x509.CertificateBuilder()
                cert_builder = cert_builder.subject_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.issuer_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.public_key(private_key.public_key())
                cert_builder = cert_builder.serial_number(x509.random_serial_number())
                cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
                cert_builder = cert_builder.not_valid_after(
                    datetime.now(timezone.utc) + timedelta(days=365)
                )
                certificate = cert_builder.sign(
                    private_key, hashes.SHA256(), backend=default_backend()
                )

                mock_pkcs.return_value = (private_key, certificate, [])

                # Mock the httpx.Client context manager and get call
                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client.__enter__.return_value = mock_client
                mock_client.__exit__.return_value = None
                mock_client_class.return_value = mock_client

                athletes = entries.fetch_club_athletes("1765")

        assert isinstance(athletes, list)
        assert len(athletes) > 0, "Expected at least one athlete from staging club"

    def test_fetch_club_athletes_response_schema(self):
        """Test that athlete responses have required fields."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ResponseStatus": "SuccessfullyCompleted",
            "Athletes": [
                {
                    "Urn": 12345,
                    "Firstname": "John",
                    "Lastname": "Doe",
                    "Dob": "2010-05-15",
                    "CompetitiveRegStatus": "Active",
                }
            ],
        }

        with (
            patch("website.entries.httpx.Client") as mock_client_class,
            patch.dict(
                os.environ,
                {
                    "EA_STAGING": "true",
                    "EA_CALL_KEY": "test_key",
                    "EA_CALL_SECRET": "test_secret",
                    "EA_CERT_PATH": "/tmp/test.pfx",
                    "EA_CERT_PASSWORD": "test_pass",
                },
            ),
            patch("website.entries.Path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"fake_pfx_data"
            )

            with patch("website.entries.pkcs12.load_key_and_certificates") as mock_pkcs:
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.backends import default_backend
                from datetime import datetime, timedelta

                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                    backend=default_backend(),
                )
                cert_builder = x509.CertificateBuilder()
                cert_builder = cert_builder.subject_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.issuer_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.public_key(private_key.public_key())
                cert_builder = cert_builder.serial_number(x509.random_serial_number())
                cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
                cert_builder = cert_builder.not_valid_after(
                    datetime.now(timezone.utc) + timedelta(days=365)
                )
                certificate = cert_builder.sign(
                    private_key, hashes.SHA256(), backend=default_backend()
                )

                mock_pkcs.return_value = (private_key, certificate, [])

                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client.__enter__.return_value = mock_client
                mock_client.__exit__.return_value = None
                mock_client_class.return_value = mock_client

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

    def test_registration_status_normalization(self):
        """Test that registration status is properly normalized."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ResponseStatus": "SuccessfullyCompleted",
            "Athletes": [
                {
                    "Urn": 12345,
                    "Firstname": "John",
                    "Lastname": "Doe",
                    "Dob": "2010-05-15",
                    "CompetitiveRegStatus": "Active",
                },
                {
                    "Urn": 67890,
                    "Firstname": "Jane",
                    "Lastname": "Smith",
                    "Dob": "2008-03-22",
                    "CompetitiveRegStatus": "Not Active",
                },
            ],
        }

        with (
            patch("website.entries.httpx.Client") as mock_client_class,
            patch.dict(
                os.environ,
                {
                    "EA_STAGING": "true",
                    "EA_CALL_KEY": "test_key",
                    "EA_CALL_SECRET": "test_secret",
                    "EA_CERT_PATH": "/tmp/test.pfx",
                    "EA_CERT_PASSWORD": "test_pass",
                },
            ),
            patch("website.entries.Path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"fake_pfx_data"
            )

            with patch("website.entries.pkcs12.load_key_and_certificates") as mock_pkcs:
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.backends import default_backend
                from datetime import datetime, timedelta

                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                    backend=default_backend(),
                )
                cert_builder = x509.CertificateBuilder()
                cert_builder = cert_builder.subject_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.issuer_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.public_key(private_key.public_key())
                cert_builder = cert_builder.serial_number(x509.random_serial_number())
                cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
                cert_builder = cert_builder.not_valid_after(
                    datetime.now(timezone.utc) + timedelta(days=365)
                )
                certificate = cert_builder.sign(
                    private_key, hashes.SHA256(), backend=default_backend()
                )

                mock_pkcs.return_value = (private_key, certificate, [])

                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client.__enter__.return_value = mock_client
                mock_client.__exit__.return_value = None
                mock_client_class.return_value = mock_client

                athletes = entries.fetch_club_athletes("1765")

        statuses = {a["RegistrationStatus"] for a in athletes}
        # Should only contain normalized values
        valid_statuses = {"Registered", "Not Registered"}
        assert statuses.issubset(valid_statuses), (
            f"Invalid statuses found: {statuses - valid_statuses}"
        )

    def test_age_category_calculation(self):
        """Test that age category calculation works for returned athletes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ResponseStatus": "SuccessfullyCompleted",
            "Athletes": [
                {
                    "Urn": 12345,
                    "Firstname": "Alice",
                    "Lastname": "Young",
                    "Dob": "2010-05-15",
                    "CompetitiveRegStatus": "Active",
                },
                {
                    "Urn": 67890,
                    "Firstname": "Bob",
                    "Lastname": "Middle",
                    "Dob": "2000-03-22",
                    "CompetitiveRegStatus": "Active",
                },
                {
                    "Urn": 11111,
                    "Firstname": "Charlie",
                    "Lastname": "Old",
                    "Dob": "1980-01-01",
                    "CompetitiveRegStatus": "Active",
                },
            ],
        }

        with (
            patch("website.entries.httpx.Client") as mock_client_class,
            patch.dict(
                os.environ,
                {
                    "EA_STAGING": "true",
                    "EA_CALL_KEY": "test_key",
                    "EA_CALL_SECRET": "test_secret",
                    "EA_CERT_PATH": "/tmp/test.pfx",
                    "EA_CERT_PASSWORD": "test_pass",
                },
            ),
            patch("website.entries.Path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"fake_pfx_data"
            )

            with patch("website.entries.pkcs12.load_key_and_certificates") as mock_pkcs:
                from cryptography.hazmat.primitives.asymmetric import rsa
                from cryptography import x509
                from cryptography.x509.oid import NameOID
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.backends import default_backend
                from datetime import datetime, timedelta

                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=2048,
                    backend=default_backend(),
                )
                cert_builder = x509.CertificateBuilder()
                cert_builder = cert_builder.subject_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.issuer_name(
                    x509.Name(
                        [x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")]
                    )
                )
                cert_builder = cert_builder.public_key(private_key.public_key())
                cert_builder = cert_builder.serial_number(x509.random_serial_number())
                cert_builder = cert_builder.not_valid_before(datetime.now(timezone.utc))
                cert_builder = cert_builder.not_valid_after(
                    datetime.now(timezone.utc) + timedelta(days=365)
                )
                certificate = cert_builder.sign(
                    private_key, hashes.SHA256(), backend=default_backend()
                )

                mock_pkcs.return_value = (private_key, certificate, [])

                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client.__enter__.return_value = mock_client
                mock_client.__exit__.return_value = None
                mock_client_class.return_value = mock_client

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


class TestEAStagingIntegration:
    """Integration tests against real England Athletics staging API.

    These tests are skipped unless EA_STAGING=true and all credentials are configured.
    They validate the actual API contract and help distinguish between:
      - API connectivity/authentication issues
      - API response format changes
      - Code logic issues
    """

    @pytest.mark.integration
    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason=(
            "Requires EA_STAGING=true, EA_CALL_KEY, EA_CALL_SECRET, "
            "EA_CERT_PATH, EA_CERT_PASSWORD, and a valid cert file. "
            "Set these if you have EA staging credentials and want to run integration tests."
        ),
    )
    def test_fetch_club_athletes_integration(self):
        """Test fetching athletes from the real staging API (happy path).

        This test validates the actual API integration. If it fails:
          - Check if the staging API is available (network/firewall issue)
          - Verify credentials in EA_CALL_KEY, EA_CALL_SECRET, EA_CERT_PATH, EA_CERT_PASSWORD
          - Confirm the certificate has not expired
          - Check if club ID "1765" still exists in staging with athletes
        """
        try:
            athletes = entries.fetch_club_athletes("1765")
        except Exception as e:
            pytest.fail(
                f"Failed to fetch athletes from staging API. "
                f"This indicates an API connectivity or authentication issue. "
                f"Error: {type(e).__name__}: {e}"
            )

        assert isinstance(athletes, list), (
            f"Expected list of athletes, got {type(athletes).__name__}. "
            f"This indicates a response format issue."
        )
        assert len(athletes) > 0, (
            "No athletes returned from club 1765. "
            "The club may not exist, have no athletes, or the API response format changed. "
            "Check the staging club data."
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not _ea_staging_configured(),
        reason=(
            "Requires EA_STAGING=true, EA_CALL_KEY, EA_CALL_SECRET, "
            "EA_CERT_PATH, EA_CERT_PASSWORD, and a valid cert file."
        ),
    )
    def test_fetch_club_athletes_response_schema_integration(self):
        """Validate the staging API response schema matches expectations.

        If this fails, the API response format may have changed. Check the EA TRAPI
        documentation and update _normalize_ea_athlete() if the API schema changed.
        """
        try:
            athletes = entries.fetch_club_athletes("1765")
        except Exception as e:
            pytest.fail(
                f"Failed to fetch athletes from staging API: {type(e).__name__}: {e}"
            )

        assert len(athletes) > 0, "No athletes returned (see test above for details)"

        # Validate required fields in the first athlete
        athlete = athletes[0]
        required_fields = [
            "IndividualRef",
            "FirstName",
            "LastName",
            "DateOfBirth",
            "RegistrationStatus",
        ]
        for field in required_fields:
            assert field in athlete, (
                f"Missing required field '{field}'. "
                f"The EA API response schema may have changed. "
                f"Athlete record: {athlete}"
            )

        # Validate types
        assert isinstance(athlete["IndividualRef"], (int, str)), (
            f"IndividualRef should be int or str, got {type(athlete['IndividualRef']).__name__}"
        )
        assert isinstance(athlete["FirstName"], str), (
            f"FirstName should be str, got {type(athlete['FirstName']).__name__}"
        )
        assert isinstance(athlete["LastName"], str), (
            f"LastName should be str, got {type(athlete['LastName']).__name__}"
        )
        assert isinstance(athlete["RegistrationStatus"], str), (
            f"RegistrationStatus should be str, got {type(athlete['RegistrationStatus']).__name__}"
        )
