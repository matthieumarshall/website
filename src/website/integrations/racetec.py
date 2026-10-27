"""Integration with RaceTec Results / Tempo Events for race results."""

from __future__ import annotations

import csv
import io
import logging
import re
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import Page, Route, async_playwright

from website.models.results import ParsedRaceWithResults, ParsedResult

_logger = logging.getLogger(__name__)

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
    await page.goto(race_url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2000)

    first_page_html = await page.content()
    race_finishers = parse_results_page_html(first_page_html)
    total_pages = parse_pager_total_pages(first_page_html)

    for page_no in range(2, total_pages + 1):
        paged_url = f"{race_url}&PageNo={page_no}"
        await page.goto(paged_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)
        paged_html = await page.content()
        race_finishers.extend(parse_results_page_html(paged_html))

    deduped: dict[int, ParsedResult] = {fin.position: fin for fin in race_finishers}
    return [deduped[pos] for pos in sorted(deduped)]


async def scrape_racetec_results(
    url: str, headless: bool = True
) -> list[ParsedRaceWithResults]:
    """Scrape all races and results from a RaceTec results URL using Playwright.

    Raises:
        RaceTecScrapeError: If scraping fails or is blocked.
    """
    if not _is_allowed_racetec_url(url):
        raise RaceTecScrapeError(
            "Invalid RaceTec URL: use an HTTPS URL on racetecresults.com"
        )

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    c_id = qs.get("CId", [""])[0]
    r_id = qs.get("RId", [""])[0]

    if not c_id or not r_id:
        raise RaceTecScrapeError(
            f"Invalid RaceTec URL: missing CId or RId query parameter ({url})"
        )

    race_results: list[ParsedRaceWithResults] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            await context.route("**/*", _guard_racetec_request)
            page = await context.new_page()

            # Navigate to the main results page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            title = await page.title()
            if "Just a moment..." in title or "Attention Required" in title:
                # Cloudflare challenge detected
                await page.wait_for_timeout(5000)
                title = await page.title()
                if "Just a moment..." in title:
                    raise RaceTecScrapeError(
                        "Scraper blocked by Cloudflare challenge. "
                        "Please use on-demand browser sync or manual CSV upload."
                    )

            html = await page.content()
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
                _logger.info("Scraping race %s (%s)", race_name, race_url)
                finishers = await _scrape_single_race(page, race_url)
                race_results.append(
                    ParsedRaceWithResults(
                        race_name=race_name,
                        eid=eid,
                        results=finishers,
                    )
                )

            await browser.close()
    except Exception as exc:
        if isinstance(exc, RaceTecScrapeError):
            raise
        raise RaceTecScrapeError(f"Failed to scrape RaceTec results: {exc}") from exc

    return race_results
