"""England Athletics TRAPI API client, age category logic, and entry eligibility."""

import os
from datetime import date, datetime, time, timezone

import duckdb
import httpx
from fastapi import HTTPException


_EA_STAGING_BASE = (
    "https://staging.myathletics.uk/TrinityAPIstaging/TrinityAPIService.svc/"
)
_EA_LIVE_BASE = "https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/"

# OXL age categories ordered junior→senior for display
_JUNIOR_CATEGORIES = frozenset({"U9", "U11", "U13", "U15", "U17"})


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

    Raises HTTPException(503) if the EA API is unreachable.
    Raises HTTPException(502) on unexpected EA API errors.
    """
    cert_path = os.environ.get("EA_CERT_PATH", "")
    cert_password = os.environ.get("EA_CERT_PASSWORD", "")
    url = f"{_ea_base_url()}race-provider/clubs/{ea_club_id}/athletes"
    try:
        # http1=True required — EA API does not support HTTP/2 with client certs
        with httpx.Client(
            cert=(cert_path, cert_password) if cert_path else None,
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

    if resp.status_code == 404:
        # Method 5 URL not found — return empty list so caller can handle
        return []
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
