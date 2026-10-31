"""Tests for RaceTec Results / Tempo Events HTML and CSV parsing."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from website.integrations import racetec
from website.integrations.racetec import (
    RaceTecScrapeError,
    _guard_racetec_request,
    _parse_retry_after,
    _RequestPacer,
    parse_csv_results,
    parse_pager_total_pages,
    parse_races_from_html,
    parse_results_page_html,
    results_to_csv,
    scrape_racetec_results,
)
from website.models.results import ParsedResult

_SAMPLE_NAV_HTML = """
<ul id="ctl00_Content_Main_divEvents" class="nav nav-tabs justify-content-center rtv3-band">
  <li class="nav-item">
    <a class="nav-link" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=1&amp;dt=0">Under 9 Girls &amp; Boys Race</a>
  </li>
  <li class="nav-item">
    <a class="nav-link" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=2&amp;dt=0">Under 11 Girls &amp; Boys Race</a>
  </li>
  <li class="nav-item">
    <a class="nav-link" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;dt=0">Senior Men's Race</a>
  </li>
  <li class="nav-item">
    <a class="nav-link" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=8&amp;dt=0">Senior Women's Race</a>
  </li>
</ul>
"""

_SAMPLE_TABLE_HTML = """
<table id="ctl00_Content_Main_tblResults" class="table rt-striped-grid">
  <thead>
    <tr><th>FAV</th><th>POS</th><th>NAME</th><th>TIME</th><th>Gen Pos</th><th>CATEGORY</th><th>GENDER</th><th>CLUB</th></tr>
  </thead>
  <tbody>
    <tr data-href="myresults.aspx?uid=1">
      <td></td>
      <td class="ltw-cell-center"><span class="rtv3-pos">1</span></td>
      <td class="ltw-cell-left"><a class="grid-name" href="myresults.aspx?uid=1">Ben Cole</a><div class="rtv3-sub">#1188</div></td>
      <td class="ltw-time">00:27:10</td>
      <td>1</td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1&amp;c=3">V40</a><div class="rtv3-sub">1 of 43</div></td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1">Male</a><div class="rtv3-sub">1 of 210</div></td>
      <td class="ltw-cell-left">Swindon Harriers</td>
    </tr>
    <tr data-href="myresults.aspx?uid=2">
      <td></td>
      <td class="ltw-cell-center"><span class="rtv3-pos">2</span></td>
      <td class="ltw-cell-left"><a class="grid-name" href="myresults.aspx?uid=2">Alex Bampton</a><div class="rtv3-sub">#1789</div></td>
      <td class="ltw-time">00:27:24</td>
      <td>2</td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1&amp;c=2">Senior Men</a><div class="rtv3-sub">1 of 72</div></td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1">Male</a><div class="rtv3-sub">2 of 210</div></td>
      <td class="ltw-cell-left">Swindon Harriers</td>
    </tr>
    <tr data-href="myresults.aspx?uid=3">
      <td></td>
      <td class="ltw-cell-center"><span class="rtv3-pos">3</span></td>
      <td class="ltw-cell-left"><a class="grid-name" href="myresults.aspx?uid=3">Simon Byrne</a><div class="rtv3-sub">#1218</div></td>
      <td class="ltw-time">00:27:56</td>
      <td>3</td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1&amp;c=2">Senior Men</a><div class="rtv3-sub">2 of 72</div></td>
      <td><a class="grid-link rtv3-chip" href="results.aspx?CId=16418&amp;RId=1006&amp;EId=7&amp;g=1">Male</a><div class="rtv3-sub">3 of 210</div></td>
      <td class="ltw-cell-left">Swindon Harriers</td>
    </tr>
  </tbody>
</table>
"""

_SAMPLE_PAGER_HTML = """
<div id="ctl00_Content_Main_divBottomPager" class="rtv3-pager-bottom">
  210 results · page 1 of 5
</div>
"""

_SINGLE_RACE_NAV_HTML = """
<a class="nav-link" href="results.aspx?CId=1&amp;RId=2&amp;EId=1">
  Senior Men's Race
</a>
"""


def _mock_playwright(pages: list[str]) -> tuple[MagicMock, MagicMock]:
    page = MagicMock()
    page.goto = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock()
    page.content = AsyncMock(side_effect=pages)
    page.title = AsyncMock(return_value="Race Results")

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.route = AsyncMock()

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)

    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=None)
    return manager, context


@pytest.fixture(autouse=True)
def disable_request_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(racetec._REQUEST_PACER, "wait", AsyncMock())


@pytest.mark.asyncio
async def test_request_pacer_waits_for_minimum_interval() -> None:
    monotonic = MagicMock(side_effect=[10.0, 10.0, 10.5, 12.0])
    sleep = AsyncMock()
    pacer = _RequestPacer(interval_seconds=2.0, monotonic=monotonic, sleep=sleep)

    await pacer.wait()
    await pacer.wait()

    sleep.assert_awaited_once_with(1.5)


def test_parse_retry_after_seconds_and_http_date() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    assert _parse_retry_after("12", now) == 12.0
    assert _parse_retry_after("Thu, 01 Jan 2026 00:00:10 GMT", now) == 10.0
    assert _parse_retry_after("not a date", now) is None


def test_parse_races_from_html() -> None:
    races = parse_races_from_html(
        _SAMPLE_NAV_HTML, base_url="https://www.racetecresults.com"
    )
    assert len(races) == 4
    assert races[0] == (
        1,
        "Under 9 Girls & Boys Race",
        "https://www.racetecresults.com/results.aspx?CId=16418&RId=1006&EId=1&dt=0",
    )
    assert races[1][0] == 2
    assert races[2] == (
        7,
        "Senior Men's Race",
        "https://www.racetecresults.com/results.aspx?CId=16418&RId=1006&EId=7&dt=0",
    )
    assert races[3][0] == 8


def test_parse_pager_total_pages() -> None:
    assert parse_pager_total_pages(_SAMPLE_PAGER_HTML) == 5
    assert parse_pager_total_pages("<div>No pager</div>") == 1
    assert parse_pager_total_pages('<a href="?PageNo=3">3</a>') == 3


def test_parse_results_page_html() -> None:
    results = parse_results_page_html(_SAMPLE_TABLE_HTML)
    assert len(results) == 3

    r1 = results[0]
    assert r1.position == 1
    assert r1.athlete_name == "Ben Cole"
    assert r1.race_number == 1188
    assert r1.time == "00:27:10"
    assert r1.category == "V40"
    assert r1.category_position == 1
    assert r1.gender == "Male"
    assert r1.gender_position == 1
    assert r1.club == "Swindon Harriers"

    r2 = results[1]
    assert r2.position == 2
    assert r2.athlete_name == "Alex Bampton"
    assert r2.race_number == 1789
    assert r2.category == "Senior Men"
    assert r2.category_position == 1
    assert r2.gender_position == 2

    r3 = results[2]
    assert r3.position == 3
    assert r3.athlete_name == "Simon Byrne"
    assert r3.race_number == 1218


def test_results_to_csv_and_parse_csv_roundtrip() -> None:
    original = [
        ParsedResult(
            position=1,
            race_number=1188,
            athlete_name="Ben Cole",
            time="00:27:10",
            category="V40",
            category_position=1,
            gender="Male",
            gender_position=1,
            club="Swindon Harriers",
        ),
        ParsedResult(
            position=2,
            race_number=1789,
            athlete_name="Alex Bampton",
            time="00:27:24",
            category="Senior Men",
            category_position=1,
            gender="Male",
            gender_position=2,
            club="Swindon Harriers",
        ),
    ]

    csv_text = results_to_csv(original)
    assert "Ben Cole" in csv_text
    assert "Alex Bampton" in csv_text

    reconstructed = parse_csv_results(csv_text)
    assert len(reconstructed) == 2
    assert reconstructed[0] == original[0]
    assert reconstructed[1] == original[1]


def test_parser_handles_unrecognized_and_malformed_rows() -> None:
    assert (
        parse_races_from_html(
            '<a href="results.aspx?CId=1&amp;RId=2&amp;EId=1">Home</a>'
        )
        == []
    )
    assert parse_results_page_html("<table><tr><td>no results</td></tr></table>") == []
    assert parse_csv_results("") == []
    assert parse_csv_results("Position,Runner\nnot-a-number,") == []


@pytest.mark.asyncio
async def test_scrape_racetec_results_reads_races_and_results() -> None:
    manager, context = _mock_playwright([_SINGLE_RACE_NAV_HTML, _SAMPLE_TABLE_HTML])
    url = "https://www.racetecresults.com/results.aspx?CId=1&RId=2"

    with patch("website.integrations.racetec.async_playwright", return_value=manager):
        races = await scrape_racetec_results(url)

    assert len(races) == 1
    assert races[0].race_name == "Senior Men's Race"
    assert len(races[0].results) == 3
    context.route.assert_awaited_once()


@pytest.mark.asyncio
async def test_scrape_racetec_results_raises_for_cloudflare_challenge() -> None:
    manager, _ = _mock_playwright([_SINGLE_RACE_NAV_HTML])
    page = manager.__aenter__.return_value.chromium.launch.return_value
    page.new_context.return_value.new_page.return_value.title = AsyncMock(
        side_effect=["Just a moment...", "Just a moment..."]
    )

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        pytest.raises(RaceTecScrapeError, match="challenge page"),
    ):
        await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )


@pytest.mark.asyncio
async def test_scrape_stops_on_challenge_in_race_page() -> None:
    manager, _ = _mock_playwright([_SINGLE_RACE_NAV_HTML, "<title>Challenge</title>"])
    page = manager.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.title = AsyncMock(side_effect=["Race Results", "Attention Required"])

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        pytest.raises(RaceTecScrapeError, match="challenge page"),
    ):
        await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    assert page.goto.await_count == 2


@pytest.mark.asyncio
async def test_scrape_honors_retry_after_and_retries_429_once() -> None:
    manager, _ = _mock_playwright([_SINGLE_RACE_NAV_HTML, _SAMPLE_TABLE_HTML])
    page = manager.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.goto = AsyncMock(
        side_effect=[
            SimpleNamespace(status=429, headers={"retry-after": "3"}),
            SimpleNamespace(status=200, headers={}),
            SimpleNamespace(status=200, headers={}),
        ]
    )
    sleep = AsyncMock()

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        patch("website.integrations.racetec._sleep_before_retry", sleep),
    ):
        races = await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    assert len(races) == 1
    assert page.goto.await_count == 3
    sleep.assert_awaited_once_with(3.0)


@pytest.mark.asyncio
async def test_scrape_stops_after_second_429() -> None:
    manager, _ = _mock_playwright([])
    page = manager.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.goto = AsyncMock(
        side_effect=[
            SimpleNamespace(status=429, headers={"retry-after": "0"}),
            SimpleNamespace(status=429, headers={"retry-after": "0"}),
        ]
    )
    sleep = AsyncMock()

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        patch("website.integrations.racetec._sleep_before_retry", sleep),
        pytest.raises(RaceTecScrapeError, match="HTTP 429"),
    ):
        await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    assert page.goto.await_count == 2
    sleep.assert_awaited_once_with(0.0)


@pytest.mark.asyncio
async def test_scrape_stops_on_http_access_denied() -> None:
    manager, _ = _mock_playwright([])
    browser = manager.__aenter__.return_value.chromium.launch.return_value
    page = browser.new_context.return_value.new_page.return_value
    page.goto.return_value = SimpleNamespace(status=403, headers={})

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        pytest.raises(RaceTecScrapeError, match="denied"),
    ):
        await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    page.goto.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_scrape_retries_server_error_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _ = _mock_playwright([_SINGLE_RACE_NAV_HTML, _SAMPLE_TABLE_HTML])
    page = manager.__aenter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.goto = AsyncMock(
        side_effect=[
            SimpleNamespace(status=503, headers={}),
            SimpleNamespace(status=200, headers={}),
            SimpleNamespace(status=200, headers={}),
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(racetec, "_EXPONENTIAL_BACKOFF", lambda _: 1.25)

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        patch("website.integrations.racetec._sleep_before_retry", sleep),
    ):
        races = await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    assert len(races) == 1
    assert page.goto.await_count == 3
    sleep.assert_awaited_once_with(1.25)


@pytest.mark.asyncio
async def test_scrape_racetec_results_wraps_browser_errors() -> None:
    manager, _ = _mock_playwright([])
    browser = manager.__aenter__.return_value.chromium.launch.return_value
    browser.new_context.return_value.new_page.return_value.goto = AsyncMock(
        side_effect=RuntimeError("connection failed")
    )

    with (
        patch("website.integrations.racetec.async_playwright", return_value=manager),
        pytest.raises(RaceTecScrapeError, match="Failed to scrape"),
    ):
        await scrape_racetec_results(
            "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
        )

    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_racetec_request_blocks_external_hosts() -> None:
    allowed_route = MagicMock()
    allowed_route.request.url = (
        "https://www.racetecresults.com/results.aspx?CId=1&RId=2"
    )
    allowed_route.continue_ = AsyncMock()
    allowed_route.abort = AsyncMock()

    blocked_route = MagicMock()
    blocked_route.request.url = "http://127.0.0.1/admin"
    blocked_route.continue_ = AsyncMock()
    blocked_route.abort = AsyncMock()

    await _guard_racetec_request(allowed_route)
    await _guard_racetec_request(blocked_route)

    allowed_route.continue_.assert_awaited_once()
    allowed_route.abort.assert_not_awaited()
    blocked_route.abort.assert_awaited_once()
    blocked_route.continue_.assert_not_awaited()


@pytest.mark.parametrize(
    "url",
    [
        "http://www.racetecresults.com/results.aspx?CId=1&RId=2",
        "https://127.0.0.1/results.aspx?CId=1&RId=2",
        "https://example.com/results.aspx?CId=1&RId=2",
        "https://user@www.racetecresults.com/results.aspx?CId=1&RId=2",
        "https://www.racetecresults.com:8443/results.aspx?CId=1&RId=2",
    ],
)
@pytest.mark.asyncio
async def test_scrape_rejects_urls_outside_racetec(url: str) -> None:
    with pytest.raises(RaceTecScrapeError, match="HTTPS URL"):
        await scrape_racetec_results(url)


@pytest.mark.asyncio
async def test_scrape_rejects_racetec_url_without_event_ids() -> None:
    with pytest.raises(RaceTecScrapeError, match="missing CId or RId"):
        await scrape_racetec_results("https://www.racetecresults.com/results.aspx")
