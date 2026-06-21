"""England Athletics TRAPI API client, age category logic, and entry eligibility."""

import os
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path

import duckdb
import httpx
from fastapi import HTTPException

try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
except ImportError:
    pkcs12 = None  # type: ignore


_EA_STAGING_BASE = (
    "https://staging.myathletics.uk/TrinityAPIstaging/TrinityAPIService.svc/"
)
_EA_LIVE_BASE = "https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/"

_JUNIOR_CATEGORIES = frozenset({"U9", "U11", "U13", "U15", "U17"})


def _get_test_athletes() -> list[dict]:
    """Return realistic test athletes for local development.

    These match the expected format from the EA TRAPI API.
    When EA_TEST_MODE=true or running in test environment, these are returned.
    """
    return [
        {
            "IndividualRef": 3361001,
            "FirstName": "Alice",
            "LastName": "Smith",
            "DateOfBirth": "2010-05-15",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361002,
            "FirstName": "Bob",
            "LastName": "Jones",
            "DateOfBirth": "2012-08-22",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361003,
            "FirstName": "Charlie",
            "LastName": "Brown",
            "DateOfBirth": "2008-03-10",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361004,
            "FirstName": "Diana",
            "LastName": "Miller",
            "DateOfBirth": "2015-11-30",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361005,
            "FirstName": "Edward",
            "LastName": "Davis",
            "DateOfBirth": "1995-07-05",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361006,
            "FirstName": "Fiona",
            "LastName": "Wilson",
            "DateOfBirth": "2014-02-18",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361007,
            "FirstName": "George",
            "LastName": "Taylor",
            "DateOfBirth": "2009-09-25",
            "RegistrationStatus": "Active",
        },
        {
            "IndividualRef": 3361008,
            "FirstName": "Hannah",
            "LastName": "Anderson",
            "DateOfBirth": "2011-12-03",
            "RegistrationStatus": "Active",
        },
    ]


def _ea_base_url() -> str:
    staging = os.environ.get("EA_STAGING", "true").lower() == "true"
    return _EA_STAGING_BASE if staging else _EA_LIVE_BASE


def _ea_headers() -> dict[str, str]:
    call_key = os.environ.get("EA_CALL_KEY", "")
    call_secret = os.environ.get("EA_CALL_SECRET", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "X-TRAPI-CALLKEY": call_key,
        "X-TRAPI-CALLSECRET": call_secret,
        "X-TRAPI-CALLDATETIME": ts,
    }


def fetch_club_athletes(ea_club_id: str) -> list[dict]:
    """Fetch all athletes for a club from the EA TRAPI API.

    Returns a list of athlete dicts. Each dict contains at minimum:
      IndividualRef (int), FirstName, LastName, DateOfBirth, RegistrationStatus.

    Raises HTTPException(503) if the EA API is unreachable or credentials are missing.
    Raises HTTPException(502) on unexpected EA API errors.
    """
    # Test mode: return dummy athletes for local development
    if os.environ.get("EA_TEST_MODE", "").lower() == "true":
        return _get_test_athletes()

    cert_path = os.environ.get("EA_CERT_PATH", "")
    cert_password = os.environ.get("EA_CERT_PASSWORD", "")
    call_key = os.environ.get("EA_CALL_KEY", "")
    call_secret = os.environ.get("EA_CALL_SECRET", "")

    # Validate required credentials
    if not cert_path or not cert_password or not call_key or not call_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "England Athletics API is not configured. "
                "Contact the league administrator."
            ),
        )

    # Load PFX certificate if needed
    cert_file_path = None
    key_file_path = None
    try:
        if cert_path.endswith(".pfx") or cert_path.endswith(".pfx.txt"):
            if not Path(cert_path).exists():
                raise HTTPException(
                    status_code=503,
                    detail="EA certificate file not found.",
                )
            with open(cert_path, "rb") as f:
                pfx_data = f.read()
            # Extract certificate and key from PFX
            try:
                private_key, certificate, additional_certs = (
                    pkcs12.load_key_and_certificates(
                        pfx_data,
                        cert_password.encode()
                        if isinstance(cert_password, str)
                        else cert_password,
                        backend=default_backend(),
                    )
                )
                if certificate is None or private_key is None:
                    raise ValueError("Certificate or private key not found in PFX file")
                # Write cert and key to temporary files
                from cryptography.hazmat.primitives import serialization

                cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )

                # Create temp files (will be cleaned up when closed)
                cert_temp = tempfile.NamedTemporaryFile(
                    mode="wb", delete=False, suffix=".pem"
                )
                cert_temp.write(cert_pem)
                cert_temp.close()
                cert_file_path = cert_temp.name

                key_temp = tempfile.NamedTemporaryFile(
                    mode="wb", delete=False, suffix=".pem"
                )
                key_temp.write(key_pem)
                key_temp.close()
                key_file_path = key_temp.name

            except Exception as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Failed to load EA certificate: {e}",
                )
        else:
            raise HTTPException(
                status_code=503,
                detail="Invalid EA certificate path.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error loading EA certificate: {e}",
        )

    url = f"{_ea_base_url()}race-provider/clubs/{ea_club_id}/athletes"
    try:
        # http1=True required — EA API does not support HTTP/2 with client certs
        with httpx.Client(
            cert=(cert_file_path, key_file_path),
            http1=True,
            timeout=10.0,
        ) as client:
            resp = client.get(url, headers=_ea_headers())
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The England Athletics system is temporarily unavailable. "
                "Please try again shortly."
            ),
        ) from exc
    finally:
        # Clean up temporary files
        if cert_file_path and Path(cert_file_path).exists():
            try:
                Path(cert_file_path).unlink()
            except Exception:
                pass
        if key_file_path and Path(key_file_path).exists():
            try:
                Path(key_file_path).unlink()
            except Exception:
                pass

    if resp.status_code == 404:
        # Method 5 URL not found — return empty list so caller can handle
        return []
    if resp.status_code == 403:
        raise HTTPException(
            status_code=503,
            detail=(
                "England Athletics API authentication failed. "
                "Contact the league administrator."
            ),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                f"England Athletics API returned an unexpected error "
                f"(status {resp.status_code}). Please try again."
            ),
        )
    data = resp.json()
    return data.get("Athletes", [])


def get_oxl_age_category(dob: date, reference_date: date) -> str:
    """Return OXL age category (U9, U11, …, Veteran) for an athlete.

    Age is calculated as of the reference_date (typically 31 Aug of the season
    start year, per UK Athletics standard).
    """
    age = (
        reference_date.year
        - dob.year
        - ((reference_date.month, reference_date.day) < (dob.month, dob.day))
    )
    if age <= 8:
        return "U9"
    if age <= 10:
        return "U11"
    if age <= 12:
        return "U13"
    if age <= 14:
        return "U15"
    if age <= 16:
        return "U17"
    if age <= 19:
        return "U20"
    if age <= 34:
        return "Senior"
    return "Veteran"


def is_junior(category: str) -> bool:
    """Return True if the age category qualifies for junior (lower) pricing."""
    return category in _JUNIOR_CATEGORIES


def is_entry_open_for_fixture(fixture_date: date) -> bool:
    """Return True if the entry deadline for a fixture has not yet passed.

    The deadline is midday UTC on the day of the fixture.
    """
    deadline = datetime.combine(fixture_date, time(12, 0), tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < deadline


def compute_fixtures_remaining(season_id: int, db: duckdb.DuckDBPyConnection) -> int:
    """Count fixtures in the season whose entry deadline has not passed."""
    rows = db.execute(
        "SELECT date FROM fixtures WHERE season_id = ?",
        [season_id],
    ).fetchall()
    return sum(1 for (fixture_date,) in rows if is_entry_open_for_fixture(fixture_date))
