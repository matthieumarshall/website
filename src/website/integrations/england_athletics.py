"""England Athletics TRAPI API client (club athlete lookups).

Credentials are read from the environment:

* ``EA_CERT_PATH`` / ``EA_CERT_PASSWORD``: PKCS#12 client certificate;
* ``EA_CALL_KEY`` / ``EA_CALL_SECRET``: API call headers;
* ``EA_STAGING`` (default ``true``): use the staging endpoint;
* ``EA_TEST_MODE``: return fixed dummy athletes for local development.
"""

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from pydantic import BaseModel, ConfigDict
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from website.errors import ServiceUnavailableError, UpstreamError
from website.models import EAAthlete

_EA_STAGING_BASE = (
    "https://staging.myathletics.uk/TrinityAPIstaging/TrinityAPIService.svc/"
)
_EA_LIVE_BASE = "https://TrinityAPI.myathletics.uk/TrinityAPIService.svc/"
_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_AUTH_FAILED = (
    "England Athletics API authentication failed. Contact the league administrator."
)

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOTENV_PATH = _PROJECT_ROOT / ".env"


class AthleteDirectory(Protocol):
    """Anything that can list a club's registered athletes."""

    def fetch_club_athletes(self, ea_club_id: str) -> list[EAAthlete]:
        """Return the athletes registered to an England Athletics club."""
        ...


class _Credentials(BaseModel):
    model_config = ConfigDict(frozen=True)

    cert_path: str
    cert_password: str
    call_key: str
    call_secret: str
    staging: bool


class TemporaryAPIError(Exception):
    """Raised when EA API returns a temporary error (5xx status code)."""


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
    return normalized.endswith((".pfx", "pfx.txt"))


def _is_latin_1(value: str) -> bool:
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def _is_test_mode() -> bool:
    return os.environ.get("EA_TEST_MODE", "").lower() == "true"


def validate_ea_header_values_for_startup() -> None:
    """Fail fast when EA header values cannot be sent as HTTP header bytes.

    Raises:
        RuntimeError: If a header value is not ISO-8859-1 encodable.
    """
    if _is_test_mode():
        return
    for name in ("EA_CALL_KEY", "EA_CALL_SECRET"):
        value = os.environ.get(name, "")
        if value and not _is_latin_1(value):
            raise RuntimeError(
                f"Invalid {name}. Value contains characters that cannot be encoded "
                "in an ISO-8859-1 HTTP header."
            )


def validate_ea_cert_path_for_startup() -> None:
    """Fail fast on invalid EA certificate path extension at app startup.

    Raises:
        RuntimeError: If ``EA_CERT_PATH`` does not name a ``.pfx`` file.
    """
    if _is_test_mode():
        logger.warning("EA startup cert validation skipped because EA_TEST_MODE=true")
        return
    cert_path = _clean_env_path(os.environ.get("EA_CERT_PATH", ""))
    if cert_path and not _is_supported_cert_path(cert_path):
        raise RuntimeError(
            "Invalid EA_CERT_PATH. Expected a path ending with '.pfx' or '.pfx.txt' "
            f"but got: {cert_path}. "
            "Example: data/TrApiLiveOxfordXCLClientCert.pfx.txt"
        )


def _test_athletes() -> list[EAAthlete]:
    """Return realistic dummy athletes, in TRAPI format, for local development."""
    people = [
        (3361001, "Alice", "Smith", "2010-05-15"),
        (3361002, "Bob", "Jones", "2012-08-22"),
        (3361003, "Charlie", "Brown", "2008-03-10"),
        (3361004, "Diana", "Miller", "2015-11-30"),
        (3361005, "Edward", "Davis", "1995-07-05"),
        (3361006, "Fiona", "Wilson", "2014-02-18"),
        (3361007, "George", "Taylor", "2009-09-25"),
        (3361008, "Hannah", "Anderson", "2011-12-03"),
    ]
    return [
        EAAthlete(
            individual_ref=ref,
            first_name=first,
            last_name=last,
            date_of_birth=dob,
            registration_status="Active",
        )
        for ref, first, last, dob in people
    ]


def _ea_base_url() -> str:
    staging = os.environ.get("EA_STAGING", "true").lower() == "true"
    return _EA_STAGING_BASE if staging else _EA_LIVE_BASE


def _ea_headers() -> httpx.Headers:
    call_key = os.environ.get("EA_CALL_KEY", "")
    call_secret = os.environ.get("EA_CALL_SECRET", "")
    for name, value in (("EA_CALL_KEY", call_key), ("EA_CALL_SECRET", call_secret)):
        if value and not _is_latin_1(value):
            logger.error("EA header value cannot be encoded as ISO-8859-1: %s", name)
            raise ServiceUnavailableError(
                f"Invalid {name}. Value cannot be encoded in an ISO-8859-1 HTTP header."
            )
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return httpx.Headers(
        [
            (b"X-TRAPI-CALLKEY", call_key.encode("latin-1")),
            (b"X-TRAPI-CALLSECRET", call_secret.encode("latin-1")),
            (b"X-TRAPI-CALLDATETIME", ts.encode("ascii")),
        ]
    )


def _normalize_registration_status(reg_status: str) -> str:
    """Map EA status text to the app's Registered/Not Registered labels."""
    normalized = reg_status.strip().lower()
    if "registered" in normalized and "not" not in normalized:
        return "Registered"
    return "Not Registered"


def _normalize_ea_athlete(raw: dict[str, object]) -> EAAthlete:
    """Normalize an EA Method 5 payload to an :class:`EAAthlete`."""
    reg_status = raw.get(
        "CompetitiveRegStatus", raw.get("RegistrationStatus", "Not Registered")
    )
    return EAAthlete.model_validate(
        {
            "IndividualRef": raw.get("Urn", raw.get("IndividualRef", 0)),
            "FirstName": raw.get("Firstname", raw.get("FirstName", "")),
            "LastName": raw.get("Lastname", raw.get("LastName", "")),
            "DateOfBirth": raw.get("Dob", raw.get("DateOfBirth", "")),
            "RegistrationStatus": _normalize_registration_status(str(reg_status)),
        }
    )


def _validate_ea_response_status(data: dict[str, object]) -> None:
    response_status = data.get("ResponseStatus")
    if response_status in {"ApiUserCredentialsIncorrect", "InvalidCall"}:
        raise ServiceUnavailableError(_AUTH_FAILED)
    if response_status != "SuccessfullyCompleted":
        raise UpstreamError("England Athletics API returned an unexpected response.")


@retry(
    retry=retry_if_exception_type((httpx.RequestError, TemporaryAPIError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_from_ea_api(
    url: str,
    headers: httpx.Headers,
    params: dict[str, str],
    cert_file_path: str,
    key_file_path: str,
) -> httpx.Response:
    """Make the API call, retrying on network errors and 5xx responses.

    Raises:
        httpx.RequestError: On network errors (after retries).
        TemporaryAPIError: On 5xx errors (after retries).
    """
    # http1=True required: the EA API does not support HTTP/2 with client certs
    with httpx.Client(
        cert=(cert_file_path, key_file_path), http1=True, timeout=10.0
    ) as client:
        resp = client.get(url, headers=headers, params=params)
        if 500 <= resp.status_code < 600:  # noqa: PLR2004 — HTTP 5xx range
            raise TemporaryAPIError(
                f"EA API returned temporary error: {resp.status_code} {resp.reason_phrase}"
            )
        return resp


def _load_credentials() -> _Credentials:
    credentials = _Credentials(
        cert_path=os.environ.get("EA_CERT_PATH", ""),
        cert_password=os.environ.get("EA_CERT_PASSWORD", ""),
        call_key=os.environ.get("EA_CALL_KEY", ""),
        call_secret=os.environ.get("EA_CALL_SECRET", ""),
        staging=os.environ.get("EA_STAGING", "true").lower() == "true",
    )
    if not all(
        (
            credentials.cert_path,
            credentials.cert_password,
            credentials.call_key,
            credentials.call_secret,
        )
    ):
        logger.error(
            "EA fetch configuration missing: required England Athletics credentials "
            "or certificate details are not configured"
        )
        raise ServiceUnavailableError(
            "England Athletics API is not configured. Contact the league administrator."
        )
    return credentials


def _read_certificate(cert_path: str) -> bytes:
    if not _is_supported_cert_path(cert_path):
        logger.error(
            "EA certificate path rejected due to unsupported extension: %s", cert_path
        )
        raise ServiceUnavailableError("Invalid EA certificate path.")
    resolved = _resolve_existing_cert_path(cert_path)
    if resolved is None:
        logger.error(
            "EA certificate file does not exist: path=%s cwd=%s project_root=%s "
            "dotenv_ea_cert_path=%s",
            cert_path,
            Path.cwd(),
            _PROJECT_ROOT,
            _read_dotenv_value("EA_CERT_PATH"),
        )
        raise ServiceUnavailableError(
            "EA certificate file not found. Check EA_CERT_PATH and ensure "
            "your shell environment is not overriding .env."
        )
    try:
        with open(resolved, "rb") as cert_file:  # noqa: PTH123 — patched in tests
            return cert_file.read()
    except OSError as exc:
        logger.error("EA certificate loading error: %s", exc, exc_info=True)
        raise ServiceUnavailableError(f"Error loading EA certificate: {exc}") from exc


def _pem_pair(pfx_data: bytes, password: str) -> tuple[bytes, bytes]:
    try:
        private_key, certificate, _additional = pkcs12.load_key_and_certificates(
            pfx_data, password.encode(), backend=default_backend()
        )
        if certificate is None or private_key is None:
            raise ValueError("Certificate or private key not found in PFX file")
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except (ValueError, TypeError) as exc:
        logger.error("EA certificate parse failed: %s", exc, exc_info=True)
        raise ServiceUnavailableError(f"Failed to load EA certificate: {exc}") from exc
    return cert_pem, key_pem


def _write_temp_pem(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem") as temp:
        temp.write(data)
        return temp.name


@contextmanager
def _client_certificate_files(credentials: _Credentials) -> Iterator[tuple[str, str]]:
    """Yield (cert, key) PEM file paths extracted from the PFX; delete them after."""
    cert_pem, key_pem = _pem_pair(
        _read_certificate(credentials.cert_path), credentials.cert_password
    )
    paths = (_write_temp_pem(cert_pem), _write_temp_pem(key_pem))
    try:
        yield paths
    finally:
        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete temporary EA PEM file %s", path)


def _request_club_athletes(
    ea_club_id: str, cert_file: str, key_file: str
) -> httpx.Response:
    url = f"{_ea_base_url()}race-provider/clubs/{ea_club_id}/individuals"
    try:
        resp = _fetch_from_ea_api(
            url=url,
            headers=_ea_headers(),
            params={"eventdate": date.today().isoformat()},
            cert_file_path=cert_file,
            key_file_path=key_file,
        )
    except httpx.RequestError as exc:
        logger.error("EA API request error: %s", exc, exc_info=True)
        raise ServiceUnavailableError(
            "The England Athletics system is temporarily unavailable. "
            "Please try again shortly."
        ) from exc
    except TemporaryAPIError as exc:
        logger.error("EA API temporary server error: %s", exc, exc_info=True)
        raise ServiceUnavailableError(
            "The England Athletics system is experiencing temporary issues. "
            "Please try again shortly."
        ) from exc
    logger.info(
        "EA API response received: status=%s reason=%s",
        resp.status_code,
        resp.reason_phrase,
    )
    return resp


def _parse_athletes(resp: httpx.Response) -> list[EAAthlete]:
    if resp.status_code == _HTTP_FORBIDDEN:
        raise ServiceUnavailableError(_AUTH_FAILED)
    if resp.status_code != _HTTP_OK:
        raise UpstreamError(
            "England Athletics API returned an unexpected error "
            f"(status {resp.status_code}). Please try again."
        )
    data = resp.json()
    _validate_ea_response_status(data)
    return [_normalize_ea_athlete(raw) for raw in data.get("Athletes") or []]


def fetch_club_athletes(ea_club_id: str) -> list[EAAthlete]:
    """Fetch all athletes for a club from the EA TRAPI API.

    Raises:
        ServiceUnavailableError: If the API is unreachable or misconfigured.
        UpstreamError: If the API returns an unexpected response.
    """
    if _is_test_mode():
        return _test_athletes()

    credentials = _load_credentials()
    logger.info(
        "EA fetch start: club_id=%s, staging=%s, cert_name=%s",
        ea_club_id,
        credentials.staging,
        Path(credentials.cert_path).name,
    )
    with _client_certificate_files(credentials) as (cert_file, key_file):
        resp = _request_club_athletes(ea_club_id, cert_file, key_file)
    athletes = _parse_athletes(resp)
    logger.info(
        "EA fetch successful: club_id=%s athletes=%s", ea_club_id, len(athletes)
    )
    return athletes


class EnglandAthleticsDirectory:
    """:class:`AthleteDirectory` backed by the live England Athletics API."""

    def fetch_club_athletes(self, ea_club_id: str) -> list[EAAthlete]:
        """Return the athletes registered to an England Athletics club."""
        return fetch_club_athletes(ea_club_id)
