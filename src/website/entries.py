"""England Athletics TRAPI API client, age category logic, and entry eligibility."""

import logging
import os
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path

import duckdb
import httpx
from fastapi import HTTPException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOTENV_PATH = _PROJECT_ROOT / ".env"


def _clean_env_path(path_value: str) -> str:
    return path_value.strip().strip('"').strip("'")


def _read_dotenv_value(key: str) -> str | None:
    if not _DOTENV_PATH.exists():
        return None
    try:
        for raw_line in _DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            lhs, rhs = line.split("=", 1)
            if lhs.strip() == key:
                return _clean_env_path(rhs)
    except OSError:
        return None
    return None


def _path_candidates(path_value: str) -> list[Path]:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return [candidate]
    return [Path.cwd() / candidate, _PROJECT_ROOT / candidate]


def _resolve_existing_cert_path(cert_path: str) -> Path | None:
    cleaned = _clean_env_path(cert_path)
    for path in _path_candidates(cleaned):
        if path.exists():
            return path

    dotenv_cert_path = _read_dotenv_value("EA_CERT_PATH")
    if dotenv_cert_path and dotenv_cert_path != cleaned:
        for path in _path_candidates(dotenv_cert_path):
            if path.exists():
                logger.warning(
                    "EA_CERT_PATH from shell env was not found; using .env value instead"
                )
                return path
    return None


def _is_supported_cert_path(cert_path: str) -> bool:
    normalized = _clean_env_path(cert_path).replace("\\", "/").lower()
    return normalized.endswith(".pfx") or normalized.endswith("pfx.txt")


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def validate_ea_header_values_for_startup() -> None:
    """Fail fast when EA header values contain non-ASCII characters."""
    if os.environ.get("EA_TEST_MODE", "").lower() == "true":
        return

    call_key = os.environ.get("EA_CALL_KEY", "")
    call_secret = os.environ.get("EA_CALL_SECRET", "")
    for name, value in (("EA_CALL_KEY", call_key), ("EA_CALL_SECRET", call_secret)):
        if value and not _is_ascii(value):
            raise RuntimeError(
                f"Invalid {name}. Value contains non-ASCII characters, but HTTP "
                "headers must be ASCII. Check for characters like '£' and replace "
                "with the exact API secret value."
            )


def validate_ea_cert_path_for_startup() -> None:
    """Fail fast on invalid EA certificate path extension at app startup."""
    if os.environ.get("EA_TEST_MODE", "").lower() == "true":
        logger.warning("EA startup cert validation skipped because EA_TEST_MODE=true")
        return

    cert_path = _clean_env_path(os.environ.get("EA_CERT_PATH", ""))
    if not cert_path:
        return

    if not _is_supported_cert_path(cert_path):
        raise RuntimeError(
            "Invalid EA_CERT_PATH. Expected a path ending with '.pfx' or '.pfx.txt' "
            f"but got: {cert_path}. "
            "Example: data/TrApiLiveOxfordXCLClientCert.pfx.txt"
        )


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
    for name, value in (
        ("EA_CALL_KEY", call_key),
        ("EA_CALL_SECRET", call_secret),
    ):
        if value and not _is_ascii(value):
            logger.error("EA header value contains non-ASCII characters: %s", name)
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Invalid {name}. Value contains non-ASCII characters. "
                    "HTTP headers must be ASCII."
                ),
            )
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "X-TRAPI-CALLKEY": call_key,
        "X-TRAPI-CALLSECRET": call_secret,
        "X-TRAPI-CALLDATETIME": ts,
    }


def _normalize_registration_status(reg_status: str) -> str:
    """Map EA status text to the app's expected Registered/Not Registered labels."""
    normalized = reg_status.strip().lower()
    if "registered" in normalized and "not" not in normalized:
        return "Registered"
    return "Not Registered"


def _normalize_ea_athlete(raw: dict) -> dict:
    """Normalize EA Method 5 payload keys to app-standard athlete keys."""
    urn = raw.get("Urn", raw.get("IndividualRef", 0))
    first_name = raw.get("Firstname", raw.get("FirstName", ""))
    last_name = raw.get("Lastname", raw.get("LastName", ""))
    dob = raw.get("Dob", raw.get("DateOfBirth", ""))
    reg_status = raw.get(
        "CompetitiveRegStatus",
        raw.get("RegistrationStatus", "Not Registered"),
    )
    return {
        "IndividualRef": urn,
        "FirstName": first_name,
        "LastName": last_name,
        "DateOfBirth": dob,
        "RegistrationStatus": _normalize_registration_status(str(reg_status)),
    }


class TemporaryAPIError(Exception):
    """Raised when EA API returns a temporary error (5xx status code)."""


@retry(
    retry=retry_if_exception_type((httpx.RequestError, TemporaryAPIError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_from_ea_api(
    url: str,
    headers: dict[str, str],
    params: dict[str, str],
    cert_file_path: str,
    key_file_path: str,
) -> httpx.Response:
    """Make the actual API call with automatic retry on transient failures.

    Args:
        url: The API endpoint URL
        headers: Request headers (auth headers)
        params: Query parameters (eventdate)
        cert_file_path: Path to certificate file
        key_file_path: Path to key file

    Returns:
        httpx.Response object

    Raises:
        httpx.RequestError: On network errors (retried)
        TemporaryAPIError: On 5xx errors (retried)
        httpx.HTTPStatusError: On other HTTP errors
    """
    with httpx.Client(
        cert=(cert_file_path, key_file_path),
        http1=True,
        timeout=10.0,
    ) as client:
        resp = client.get(url, headers=headers, params=params)

        # Retry on server errors (5xx)
        if 500 <= resp.status_code < 600:
            raise TemporaryAPIError(
                f"EA API returned temporary error: {resp.status_code} {resp.reason_phrase}"
            )

        return resp


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
    ea_staging = os.environ.get("EA_STAGING", "true").lower() == "true"

    cert_name = Path(cert_path).name if cert_path else "<unset>"
    logger.info(
        "EA fetch start: club_id=%s, staging=%s, cert_name=%s",
        ea_club_id,
        ea_staging,
        cert_name,
    )

    # Validate required credentials
    if not cert_path or not cert_password or not call_key or not call_secret:
        logger.error(
            "EA fetch configuration missing: has_cert_path=%s has_cert_password=%s "
            "has_call_key=%s has_call_secret=%s",
            bool(cert_path),
            bool(cert_password),
            bool(call_key),
            bool(call_secret),
        )
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
        logger.warning("EA certificate path raw value: %s", cert_path)
        if _is_supported_cert_path(cert_path):
            resolved_cert_path = _resolve_existing_cert_path(cert_path)
            if resolved_cert_path is None:
                logger.error(
                    "EA certificate file does not exist: path=%s cwd=%s "
                    "project_root=%s dotenv_ea_cert_path=%s",
                    cert_path,
                    Path.cwd(),
                    _PROJECT_ROOT,
                    _read_dotenv_value("EA_CERT_PATH"),
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "EA certificate file not found. Check EA_CERT_PATH and ensure "
                        "your shell environment is not overriding .env."
                    ),
                )
            logger.warning("EA certificate file found at path: %s", resolved_cert_path)
            with open(resolved_cert_path, "rb") as f:
                pfx_data = f.read()
            logger.debug(
                "EA certificate file loaded: bytes=%s name=%s",
                len(pfx_data),
                resolved_cert_path.name,
            )
            # Extract certificate and key from PFX
            try:
                private_key, certificate, _additional_certs = (
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

                logger.warning(
                    "EA certificate extracted to temporary PEM files successfully"
                )

            except Exception as e:
                logger.error("EA certificate parse failed: %s", e, exc_info=True)
                raise HTTPException(
                    status_code=503,
                    detail=f"Failed to load EA certificate: {e}",
                ) from e
        else:
            logger.error(
                "EA certificate path rejected due to unsupported extension: %s",
                cert_path,
            )
            raise HTTPException(
                status_code=503,
                detail="Invalid EA certificate path.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("EA certificate loading error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Error loading EA certificate: {e}",
        ) from e

    # Staging supports the club-athletes Method 5 route as:
    # race-provider/clubs/{clubId}/individuals?eventdate=YYYY-MM-DD
    event_date = date.today().isoformat()
    url = f"{_ea_base_url()}race-provider/clubs/{ea_club_id}/individuals"
    try:
        # http1=True required — EA API does not support HTTP/2 with client certs
        # Automatic retries are applied on network errors and 5xx status codes
        resp = _fetch_from_ea_api(
            url=url,
            headers=_ea_headers(),
            params={"eventdate": event_date},
            cert_file_path=cert_file_path,
            key_file_path=key_file_path,
        )
        logger.warning(
            "EA API response received: status=%s reason=%s",
            resp.status_code,
            resp.reason_phrase,
        )
    except httpx.RequestError as exc:
        logger.error("EA API request error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "The England Athletics system is temporarily unavailable. "
                "Please try again shortly."
            ),
        ) from exc
    except TemporaryAPIError as exc:
        logger.error("EA API temporary server error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "The England Athletics system is experiencing temporary issues. "
                "Please try again shortly."
            ),
        ) from exc
    finally:
        # Clean up temporary files
        if cert_file_path and Path(cert_file_path).exists():
            try:
                Path(cert_file_path).unlink()
            except OSError:
                pass
        if key_file_path and Path(key_file_path).exists():
            try:
                Path(key_file_path).unlink()
            except OSError:
                pass

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
    athletes = data.get("Athletes") or []
    logger.warning(
        "EA fetch successful: club_id=%s athletes=%s", ea_club_id, len(athletes)
    )
    return [_normalize_ea_athlete(a) for a in athletes]


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


def check_allocation(
    season_id: int, club_id: int, count_to_add: int, db: duckdb.DuckDBPyConnection
) -> bool:
    """Check if adding count_to_add athletes would exceed the club's allocation.

    Returns True if the addition is allowed, False if it would exceed allocation.
    """
    from website import repository

    allocation = repository.get_club_allocation(db, season_id, club_id)
    if allocation is None:
        # No allocation set - prevent any entries
        return False
    current_count = repository.get_club_athlete_count(db, season_id, club_id)
    return current_count + count_to_add <= allocation
