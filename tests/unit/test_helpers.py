"""Tests for CSRF, rich-text, timetable and geocoding helpers."""

import types
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from website.integrations.geocoding import geocode_address
from website.models.fixtures import parse_timetable_json as parse_timetable_from_json
from website.richtext import post_summary, safe_referer_path
from website.web.csrf import validate_csrf


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
        validate_csrf(request, "abc123")  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]

    def test_raises_403_when_token_mismatches(self) -> None:
        request = _make_request({"csrf_token": "correct"})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "wrong")  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
        assert exc_info.value.status_code == 403

    def test_raises_403_when_no_session_token(self) -> None:
        request = _make_request({})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "anything")  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
        assert exc_info.value.status_code == 403

    def test_raises_403_when_session_token_is_none(self) -> None:
        request = _make_request({"csrf_token": None})
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf(request, "anything")  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
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
        mock_client.__enter__ = MagicMock(
            side_effect=httpx.ConnectError("network failure")
        )
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "website.integrations.geocoding.httpx.Client", return_value=mock_client
        ):
            result = geocode_address("some invalid address")

        assert result is None

    def test_returns_none_on_http_error(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPError("HTTP 500")

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch(
            "website.integrations.geocoding.httpx.Client",
            return_value=mock_client_instance,
        ):
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

        with patch(
            "website.integrations.geocoding.httpx.Client",
            return_value=mock_client_instance,
        ):
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

        with patch(
            "website.integrations.geocoding.httpx.Client",
            return_value=mock_client_instance,
        ):
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
        result = parse_timetable_from_json(None)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
        assert result == []


# ---------------------------------------------------------------------------
# post_summary
# ---------------------------------------------------------------------------


class TestPostSummary:
    def test_empty_or_none_returns_empty_string(self) -> None:
        assert post_summary("", 1) == ""
        assert post_summary(None, 1) == ""  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]

    def test_short_post_returns_original_content(self) -> None:
        content = "<p>This is a short post under 300 characters.</p>"
        assert post_summary(content, 1) == content
        assert "see more" not in post_summary(content, 1)

    def test_long_post_truncates_at_word_boundary_and_adds_link(self) -> None:
        words = ["cross", "country", "league", "oxfordshire", "runners"] * 20
        long_text = "<p>" + " ".join(words) + "</p>"
        assert len(long_text) > 300

        result = post_summary(long_text, 10, length=200)
        assert 'href="/news/10"' in result
        assert "see more</a>" in result
        assert 'aria-label="See more of this post"' in result
        assert result.endswith("</p>")
        # Check it does not cut a word in half
        body = result.replace(
            '<a href="/news/10" aria-label="See more of this post">see more</a>', ""
        )
        assert not body.endswith("crossc")

    def test_long_post_with_nested_tags_balances_html(self) -> None:
        content = (
            "<p>Announcement: "
            + "word " * 50
            + "<strong>important finish</strong> more details to follow.</p>"
        )
        result = post_summary(content, 7, length=250)
        assert 'href="/news/7"' in result
        assert "see more</a>" in result
        # Ensure tags are balanced and clean
        assert result.count("<p>") == result.count("</p>")
        assert result.count("<strong>") == result.count("</strong>")
        assert result.endswith("</p>")

    def test_plain_text_without_paragraph_tags(self) -> None:
        plain_text = "word " * 100
        result = post_summary(plain_text, 5, length=100)
        assert 'href="/news/5"' in result
        assert "see more</a>" in result
