"""Integration with RaceTec Results / Tempo Events for race results."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Route, async_playwright
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    wait_random_exponential,
)

from website.models.results import ParsedRaceWithResults, ParsedResult

_logger = logging.getLogger(__name__)
_MIN_REQUEST_INTERVAL_SECONDS = 2.0
_MAX_NAVIGATION_ATTEMPTS = 3
_MAX_BACKOFF_SECONDS = 60.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_RANGE = range(500, 600)
_HTTP_CLIENT_ERROR_START = 400
_HTTP_DENIED_STATUSES = (401, 403)

_EVENT_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']*EId=(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_POS_RE = re.compile(r'class=["\'][^"\']*rtv3-pos[^"\']*["\']>(\d+)<', re.IGNORECASE)
_NAME_RE = re.compile(
    r'<a\s+class=["\'][^"\']*grid-name[^"\']*["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_BIB_RE = re.compile(
    r'<div\s+class=["\'][^"\']*rtv3-sub[^"\']*["\']>#?(\d+)</div>',
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r'<td\s+class=["\'][^"\']*ltw-time[^"\']*["\'][^>]*>(\d{1,2}:\d{2}(?::\d{2})?)</td>',
    re.IGNORECASE,
)
_CHIP_RE = re.compile(
    r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*rtv3-chip[^"\']*["\'][^>]*>(.*?)</a>'
    r"(?:\s*<div\b[^>]*rtv3-sub[^>]*>(\d+)\s+of\s+\d+</div>)?|"
    r'<a\b[^>]*class=["\'][^"\']*rtv3-chip[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    r"(?:\s*<div\b[^>]*rtv3-sub[^>]*>(\d+)\s+of\s+\d+</div>)?",
    re.IGNORECASE | re.DOTALL,
)
_PAGER_TOTAL_RE = re.compile(r"page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)
_PAGENO_PARAM_RE = re.compile(r"PageNo=(\d+)", re.IGNORECASE)
_ALLOWED_RACETEC_HOSTS = frozenset({"racetecresults.com", "www.racetecresults.com"})


_MIN_FINISHER_CELLS = 10
_CSV_COL_MAPPINGS: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("pos",), ("cat", "gen"), "position"),
    (("race no", "bib", "number"), (), "race_number"),
    (("name", "athlete"), (), "name"),
    (("time",), (), "time"),
    (("cat pos",), (), "cat_pos"),
    (("category", "cat"), (), "category"),
    (("gen pos",), (), "gen_pos"),
    (("gender", "sex"), (), "gender"),
    (("club", "team"), (), "club"),
]


class RaceTecScrapeError(Exception):
    """Raised when fetching or scraping RaceTec results fails."""


class _RetryableNavigationError(Exception):
    def __init__(self, status: int | None, retry_after: float | None) -> None:
        self.status = status
        self.retry_after = retry_after


class _RequestPacer:
    def __init__(
        self,
        interval_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._next_request_at - self._monotonic()
            if delay > 0:
                await self._sleep(delay)
            self._next_request_at = self._monotonic() + self._interval_seconds


_REQUEST_PACER = _RequestPacer(_MIN_REQUEST_INTERVAL_SECONDS)
_EXPONENTIAL_BACKOFF = wait_random_exponential(multiplier=1.0, max=_MAX_BACKOFF_SECONDS)


def _is_allowed_racetec_url(url: str) -> bool:
    """Return whether a URL targets the HTTPS RaceTec results service."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in _ALLOWED_RACETEC_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


async def _guard_racetec_request(route: Route) -> None:
    """Prevent browser requests and redirects to hosts outside RaceTec Results."""
    if _is_allowed_racetec_url(route.request.url):
        await route.continue_()
    else:
        await route.abort()


def _clean_text(raw: str) -> str:
    """Strip tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_races_from_html(
    html: str, base_url: str = "https://www.racetecresults.com"
) -> list[tuple[int, str, str]]:
    """Extract (eid, race_name, full_url) from race navigation links in HTML."""
    races: list[tuple[int, str, str]] = []
    seen_eids: set[int] = set()

    for match in _EVENT_LINK_RE.finditer(html):
        href = match.group(1).replace("&amp;", "&")
        eid_str = match.group(2)
        raw_name = match.group(3)
        try:
            eid = int(eid_str)
        except ValueError:
            continue

        name = _clean_text(raw_name)
        if not name or name.lower() in ("results", "details", "home"):
            continue

        if eid not in seen_eids:
            seen_eids.add(eid)
            full_url = urljoin(base_url, href)
            races.append((eid, name, full_url))

    return races


def parse_pager_total_pages(html: str) -> int:
    """Extract total pages count from bottom pager HTML."""
    match = _PAGER_TOTAL_RE.search(html)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    # Fallback: check max PageNo in pager links
    pages = [int(p) for p in _PAGENO_PARAM_RE.findall(html)]
    return max(pages) if pages else 1


def _parse_row_chips(row_html: str) -> tuple[str, int | None, str, int | None]:
    category = ""
    category_position = None
    gender = ""
    gender_position = None

    for chip_match in _CHIP_RE.finditer(row_html):
        if chip_match.group(1):
            href = chip_match.group(1).replace("&amp;", "&")
            chip_text = _clean_text(chip_match.group(2))
            pos_str = chip_match.group(3)
        else:
            href = chip_match.group(4).replace("&amp;", "&")
            chip_text = _clean_text(chip_match.group(5))
            pos_str = chip_match.group(6)

        sub_pos = int(pos_str) if pos_str else None
        if re.search(r"[&?]c=\d+", href, re.IGNORECASE):
            category = chip_text
            category_position = sub_pos
        elif re.search(r"[&?]g=\d+", href, re.IGNORECASE):
            gender = chip_text
            gender_position = sub_pos

    return category, category_position, gender, gender_position


def _extract_club(
    row_html: str, athlete_name: str, category: str, gender: str
) -> str | None:
    cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL)
    if len(cells) >= _MIN_FINISHER_CELLS:
        last_cell = _clean_text(cells[-1])
        if last_cell and not re.match(r"^\d{1,2}:\d{2}", last_cell):
            return last_cell

    for cell in reversed(cells):
        cleaned = _clean_text(cell)
        if (
            cleaned
            and cleaned not in (athlete_name, category, gender)
            and not re.match(r"^\d{1,2}:\d{2}", cleaned)
            and not re.match(r"^\d+$", cleaned)
        ):
            return cleaned
    return None


def _parse_result_row(row_html: str) -> ParsedResult | None:
    pos_match = _POS_RE.search(row_html)
    name_match = _NAME_RE.search(row_html)
    if not pos_match or not name_match:
        return None

    try:
        position = int(pos_match.group(1))
    except ValueError:
        return None

    athlete_name = _clean_text(name_match.group(1))
    if not athlete_name:
        return None

    bib_match = _BIB_RE.search(row_html)
    race_number = int(bib_match.group(1)) if bib_match else None

    time_match = _TIME_RE.search(row_html)
    time_str = time_match.group(1) if time_match else ""

    category, cat_pos, gender, gen_pos = _parse_row_chips(row_html)
    club = _extract_club(row_html, athlete_name, category, gender)

    return ParsedResult(
        position=position,
        race_number=race_number,
        athlete_name=athlete_name,
        time=time_str,
        category=category,
        category_position=cat_pos,
        gender=gender,
        gender_position=gen_pos,
        club=club,
    )


def parse_results_page_html(html: str) -> list[ParsedResult]:
    """Parse finisher rows from a RaceTec results table HTML string."""
    results: list[ParsedResult] = []

    table_match = re.search(
        r"<table\b[^>]*(?:tblResults|rt-striped-grid)[^>]*>(.*?)</table>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    search_scope = table_match.group(1) if table_match else html

    for row_match in _ROW_RE.finditer(search_scope):
        parsed = _parse_result_row(row_match.group(1))
        if parsed is not None:
            results.append(parsed)

    return results


def results_to_csv(results: list[ParsedResult]) -> str:
    """Format a list of parsed results as CSV text matching website columns."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Pos",
            "Race No",
            "Name",
            "Time",
            "Category",
            "Cat Pos",
            "Gender",
            "Gen Pos",
            "Club",
        ]
    )
    for r in results:
        writer.writerow(
            [
                r.position,
                r.race_number or "",
                r.athlete_name,
                r.time,
                r.category,
                r.category_position or "",
                r.gender,
                r.gender_position or "",
                r.club or "",
            ]
        )
    return output.getvalue()


def _map_csv_col(normalized: str) -> str | None:
    for includes, excludes, field in _CSV_COL_MAPPINGS:
        has_include = any(k in normalized for k in includes)
        has_exclude = any(k in normalized for k in excludes)
        if has_include and not has_exclude:
            return field
    return None


def _map_csv_headers(header: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for idx, col in enumerate(header):
        normalized = col.strip().lower().replace("_", " ")
        target = _map_csv_col(normalized)
        if target and target not in col_map:
            col_map[target] = idx
    return col_map


def _get_field(row: list[str], col_map: dict[str, int], key: str) -> str:
    idx = col_map.get(key)
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def _parse_csv_row(row: list[str], col_map: dict[str, int]) -> ParsedResult | None:
    pos_str = _get_field(row, col_map, "position")
    name = _get_field(row, col_map, "name")
    if not pos_str or not name:
        return None

    try:
        position = int(pos_str)
    except ValueError:
        return None

    bib_str = _get_field(row, col_map, "race_number").lstrip("#")
    bib = int(bib_str) if bib_str.isdigit() else None

    cat_pos_str = _get_field(row, col_map, "cat_pos")
    cat_pos = int(cat_pos_str) if cat_pos_str.isdigit() else None

    gen_pos_str = _get_field(row, col_map, "gen_pos")
    gen_pos = int(gen_pos_str) if gen_pos_str.isdigit() else None

    return ParsedResult(
        position=position,
        race_number=bib,
        athlete_name=name,
        time=_get_field(row, col_map, "time"),
        category=_get_field(row, col_map, "category"),
        category_position=cat_pos,
        gender=_get_field(row, col_map, "gender"),
        gender_position=gen_pos,
        club=_get_field(row, col_map, "club") or None,
    )


def parse_csv_results(csv_text: str) -> list[ParsedResult]:
    """Parse CSV text into a list of ParsedResult objects."""
    reader = csv.reader(io.StringIO(csv_text.strip()))
    header = next(reader, None)
    if not header:
        return []

    col_map = _map_csv_headers(header)
    results: list[ParsedResult] = []

    for row in reader:
        if not row or not any(row):
            continue
        parsed = _parse_csv_row(row, col_map)
        if parsed is not None:
            results.append(parsed)

    return sorted(results, key=lambda r: r.position)


async def _scrape_single_race(page: Page, race_url: str) -> list[ParsedResult]:
    """Scrape all paginated finisher rows for one race tab."""
    _, first_page_html = await _navigate_and_read(
        page, race_url, timeout_ms=20000, wait_ms=2000
    )
    race_finishers = parse_results_page_html(first_page_html)
    total_pages = parse_pager_total_pages(first_page_html)

    for page_no in range(2, total_pages + 1):
        paged_url = f"{race_url}&PageNo={page_no}"
        _, paged_html = await _navigate_and_read(
            page, paged_url, timeout_ms=20000, wait_ms=1500
        )
        race_finishers.extend(parse_results_page_html(paged_html))

    deduped: dict[int, ParsedResult] = {fin.position: fin for fin in race_finishers}
    return [deduped[pos] for pos in sorted(deduped)]


def _parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse an HTTP Retry-After value as seconds from now."""
    if not value:
        return None

    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - (now or datetime.now(UTC))).total_seconds()

    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def _response_retry_after(response: object) -> float | None:
    headers = getattr(response, "headers", {})
    value = headers.get("retry-after") or headers.get("Retry-After")
    return _parse_retry_after(value)


def _is_challenge_page(title: str, html: str) -> bool:
    content = f"{title}\n{html[:200_000]}".casefold()
    return any(
        marker in content
        for marker in (
            "just a moment...",
            "attention required",
            "cf-chl-",
            "cf-challenge",
            "checking your browser",
        )
    )


async def _navigate_once(
    page: Page, url: str, timeout_ms: int, wait_ms: int
) -> tuple[str, str]:
    await _REQUEST_PACER.wait()
    try:
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=timeout_ms
        )
    except PlaywrightError as exc:
        raise _RetryableNavigationError(status=None, retry_after=None) from exc

    if response is not None:
        status = response.status
        if status == _HTTP_TOO_MANY_REQUESTS or status in _HTTP_SERVER_ERROR_RANGE:
            raise _RetryableNavigationError(
                status=status,
                retry_after=_response_retry_after(response),
            )
        if status in _HTTP_DENIED_STATUSES:
            _logger.warning("RaceTec denied a results request (HTTP %s)", status)
            raise RaceTecScrapeError(
                f"RaceTec denied the results request (HTTP {status}); sync stopped."
            )
        if status >= _HTTP_CLIENT_ERROR_START:
            _logger.error("RaceTec results request failed (HTTP %s)", status)
            raise RaceTecScrapeError(f"RaceTec results request failed (HTTP {status}).")

    await page.wait_for_timeout(wait_ms)
    title = await page.title()
    html = await page.content()
    if _is_challenge_page(title, html):
        _logger.warning("RaceTec challenge page detected; sync stopped")
        raise RaceTecScrapeError(
            "RaceTec challenge page detected; sync stopped without retry."
        )
    return title, html


def _stop_navigation_retries(
    retry_after_retry_used: list[bool],
) -> Callable[[RetryCallState], bool]:
    def stop(state: RetryCallState) -> bool:
        if state.attempt_number >= _MAX_NAVIGATION_ATTEMPTS:
            return True
        if retry_after_retry_used[0]:
            return True
        exception = state.outcome.exception() if state.outcome else None
        if (
            isinstance(exception, _RetryableNavigationError)
            and exception.status == _HTTP_TOO_MANY_REQUESTS
        ):
            retry_after_retry_used[0] = True
        return False

    return stop


def _wait_before_navigation_retry(state: RetryCallState) -> float:
    exception = state.outcome.exception() if state.outcome else None
    if (
        isinstance(exception, _RetryableNavigationError)
        and exception.retry_after is not None
    ):
        return exception.retry_after
    return _EXPONENTIAL_BACKOFF(state)


def _log_navigation_retry(state: RetryCallState) -> None:
    exception = state.outcome.exception() if state.outcome else None
    if not isinstance(exception, _RetryableNavigationError):
        return
    delay = state.next_action.sleep if state.next_action is not None else 0.0
    if exception.status is not None:
        _logger.warning(
            "RaceTec returned HTTP %s; retrying after %.1f seconds",
            exception.status,
            delay,
        )
    else:
        _logger.warning("RaceTec navigation failed; retrying after %.1f seconds", delay)


async def _navigate_and_read(
    page: Page, url: str, timeout_ms: int, wait_ms: int
) -> tuple[str, str]:
    retry_after_retry_used = [False]
    retrying = AsyncRetrying(
        retry=retry_if_exception_type(_RetryableNavigationError),
        stop=_stop_navigation_retries(retry_after_retry_used),
        wait=_wait_before_navigation_retry,
        before_sleep=_log_navigation_retry,
        sleep=_sleep_before_retry,
        reraise=True,
    )
    try:
        return await retrying(_navigate_once, page, url, timeout_ms, wait_ms)
    except _RetryableNavigationError as exc:
        status_text = (
            f"HTTP {exc.status}" if exc.status is not None else "navigation error"
        )
        _logger.error("RaceTec request failed after retries (%s)", status_text)
        raise RaceTecScrapeError(
            f"RaceTec request failed after retries ({status_text})."
        ) from exc


async def _sleep_before_retry(delay: float) -> None:
    await asyncio.sleep(delay)


async def scrape_racetec_results(
    url: str, headless: bool = True
) -> list[ParsedRaceWithResults]:
    """Scrape all races and results from a RaceTec results URL using Playwright.

    Raises:
        RaceTecScrapeError: If scraping fails or is blocked.
    """
    if not _is_allowed_racetec_url(url):
        _logger.warning("Rejected a RaceTec scrape URL outside the allowed host")
        raise RaceTecScrapeError(
            "Invalid RaceTec URL: use an HTTPS URL on racetecresults.com"
        )

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    c_id = qs.get("CId", [""])[0]
    r_id = qs.get("RId", [""])[0]

    if not c_id or not r_id:
        _logger.warning("Rejected a RaceTec URL missing required event parameters")
        raise RaceTecScrapeError("Invalid RaceTec URL: missing CId or RId parameter.")

    race_results: list[ParsedRaceWithResults] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                await context.route("**/*", _guard_racetec_request)
                page = await context.new_page()

                title, html = await _navigate_and_read(
                    page, url, timeout_ms=30000, wait_ms=3000
                )
                base_site = f"{parsed.scheme}://{parsed.netloc}"
                races = parse_races_from_html(html, base_url=base_site)

                if not races:
                    # Fallback: maybe the URL directly points to a single EId
                    eid_param = qs.get("EId", [None])[0]
                    eid = int(eid_param) if eid_param and eid_param.isdigit() else None
                    races = [(eid or 1, title or "Race Results", url)]

                for eid, race_name, race_url in races:
                    if not _is_allowed_racetec_url(race_url):
                        raise RaceTecScrapeError(
                            "RaceTec page linked to a results URL outside "
                            "racetecresults.com"
                        )
                    _logger.info("Scraping RaceTec event %s (%s)", eid, race_name)
                    finishers = await _scrape_single_race(page, race_url)
                    race_results.append(
                        ParsedRaceWithResults(
                            race_name=race_name,
                            eid=eid,
                            results=finishers,
                        )
                    )
            finally:
                await browser.close()
    except Exception as exc:
        if isinstance(exc, RaceTecScrapeError):
            raise
        _logger.error("RaceTec scrape failed (%s)", type(exc).__name__)
        raise RaceTecScrapeError(
            f"Failed to scrape RaceTec results ({type(exc).__name__})."
        ) from exc

    finisher_count = sum(len(race.results) for race in race_results)
    if finisher_count == 0:
        _logger.warning("RaceTec scrape returned no finisher results")
    else:
        _logger.info(
            "RaceTec scrape completed with %s race(s) and %s finisher(s)",
            len(race_results),
            finisher_count,
        )
    return race_results
