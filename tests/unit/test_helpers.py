"""Tests for website.helpers module."""

import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from website.helpers import (
    geocode_address,
    parse_timetable_from_json,
    safe_referer_path,
    validate_csrf,
)


def _make_request(session: dict | None = None) -> object:
    """Build a minimal mock Request with the given session dict."""
    return types.SimpleNamespace(session=dict(session or {}))


# ---------------------------------------------------------------------------
# validate_csrf
# ---------------------------------------------------------------------------


class TestValidateCsrf:
    def test_passes_when_tokens_match(self) -> None:
        request = _make_request({"csrf_token": "abc123"})
        # Should not raise
        validate_csrf(request, "abc123")  # type: ignore[arg-type]

    def test_raises_403_when_token_mismatches(self) -> None:
        request = _make_request({"csrf_token": "correct"})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "wrong")  # type: ignore[arg-type]
        assert exc_info.value.status_code == 403

    def test_raises_403_when_no_session_token(self) -> None:
        request = _make_request({})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "anything")  # type: ignore[arg-type]
        assert exc_info.value.status_code == 403

    def test_raises_403_when_session_token_is_none(self) -> None:
        request = _make_request({"csrf_token": None})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "anything")  # type: ignore[arg-type]
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# safe_referer_path
# ---------------------------------------------------------------------------


class TestSafeRefererPath:
    def test_empty_string_returns_news(self) -> None:
        assert safe_referer_path("") == "/news"

    def test_full_url_with_path_returns_path(self) -> None:
        assert safe_referer_path("https://example.com/fixtures") == "/fixtures"

    def test_full_url_with_nested_path(self) -> None:
        assert safe_referer_path("http://localhost/news?page=2") == "/news"

    def test_url_with_no_path_returns_news(self) -> None:
        # urlparse of "https://example.com" returns path=""
        assert safe_referer_path("https://example.com") == "/news"

    def test_bare_relative_path(self) -> None:
        assert safe_referer_path("/account") == "/account"


# ---------------------------------------------------------------------------
# geocode_address
# ---------------------------------------------------------------------------


class TestGeocodeAddress:
    def test_returns_none_on_network_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=Exception("network failure"))
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("website.helpers.httpx.Client", return_value=mock_client):
            result = geocode_address("some invalid address")

        assert result is None

    def test_returns_none_on_http_error(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("website.helpers.httpx.Client", return_value=mock_client_instance):
            result = geocode_address("bad address")

        assert result is None

    def test_returns_coordinates_on_success(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [{"lat": "51.5", "lon": "-0.1"}]

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("website.helpers.httpx.Client", return_value=mock_client_instance):
            result = geocode_address("London")

        assert result == (51.5, -0.1)

    def test_returns_none_when_no_results(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("website.helpers.httpx.Client", return_value=mock_client_instance):
            result = geocode_address("NonExistentPlace12345")

        assert result is None


# ---------------------------------------------------------------------------
# parse_timetable_from_json
# ---------------------------------------------------------------------------


class TestParseTimetableFromJson:
    def test_returns_empty_list_for_invalid_json(self) -> None:
        result = parse_timetable_from_json("not valid json {{{")
        assert result == []

    def test_returns_empty_list_for_empty_string(self) -> None:
        result = parse_timetable_from_json("")
        assert result == []

    def test_returns_entries_for_valid_json(self) -> None:
        import json

        data = json.dumps([{"event": "Start", "time": "09:00"}])
        result = parse_timetable_from_json(data)
        assert len(result) == 1
        assert result[0].event == "Start"
        assert result[0].time == "09:00"

    def test_skips_items_without_event_and_time(self) -> None:
        import json

        data = json.dumps(
            [{"event": "", "time": ""}, {"event": "Lunch", "time": "12:00"}]
        )
        result = parse_timetable_from_json(data)
        assert len(result) == 1
        assert result[0].event == "Lunch"

    def test_skips_non_dict_items(self) -> None:
        import json

        data = json.dumps(["not_a_dict", {"event": "Start", "time": "09:00"}])
        result = parse_timetable_from_json(data)
        assert len(result) == 1

    def test_returns_empty_list_for_null_input(self) -> None:
        result = parse_timetable_from_json(None)  # type: ignore[arg-type]
        assert result == []
