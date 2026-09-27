"""Address geocoding via the OpenStreetMap Nominatim API."""

import logging
from typing import Protocol

import httpx

_logger = logging.getLogger(__name__)
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires a descriptive User-Agent.
_USER_AGENT = "FixtureWebsite/1.0 (fixture location geocoder)"

Coordinates = tuple[float, float]


class Geocoder(Protocol):
    """Anything that can turn an address into coordinates."""

    def geocode(self, address: str) -> Coordinates | None:
        """Return ``(latitude, longitude)`` for *address*, or None."""
        ...


def geocode_address(address: str) -> Coordinates | None:
    """Geocode *address* to ``(latitude, longitude)`` using Nominatim.

    Geocoding is best effort: returns None if the address cannot be found or
    the request fails.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                _NOMINATIM_URL,
                params={"q": address, "format": "json", "limit": "1"},
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
            results = response.json()
            if results:
                return (float(results[0]["lat"]), float(results[0]["lon"]))
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        _logger.warning("Failed to geocode address: %s", address)
    return None


class NominatimGeocoder:
    """:class:`Geocoder` backed by the public Nominatim service."""

    def geocode(self, address: str) -> Coordinates | None:
        """Return ``(latitude, longitude)`` for *address*, or None."""
        return geocode_address(address)
