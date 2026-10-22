"""Tests for RaceTec Results / Tempo Events HTML and CSV parsing."""

from website.integrations.racetec import (
    parse_csv_results,
    parse_pager_total_pages,
    parse_races_from_html,
    parse_results_page_html,
    results_to_csv,
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
