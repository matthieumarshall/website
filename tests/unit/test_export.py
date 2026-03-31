"""Unit tests for CSV and PDF export helpers and export routes."""

import csv
import io

from website.export import build_csv, build_pdf, filter_results
from website.models import Result

from .test_results import (
    _make_fixture,
    _make_race,
    _make_result,
    _make_season,
)


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------


def _result(
    position: int = 1,
    athlete_name: str = "Alice Smith",
    time: str = "00:30:00",
    category: str = "Senior Women",
    gender: str = "Female",
    race_number: int | None = 100,
    category_position: int | None = 1,
    gender_position: int | None = 1,
    club: str | None = "Test AC",
    race_id: int = 1,
) -> Result:
    return Result(
        id=1,
        race_id=race_id,
        position=position,
        race_number=race_number,
        athlete_name=athlete_name,
        time=time,
        category=category,
        category_position=category_position,
        gender=gender,
        gender_position=gender_position,
        club=club,
    )


# ---------------------------------------------------------------------------
# filter_results
# ---------------------------------------------------------------------------


def test_filter_by_category():
    results = [
        _result(category="V40"),
        _result(category="Senior Women"),
    ]
    filtered = filter_results(results, category="V40")
    assert len(filtered) == 1
    assert filtered[0].category == "V40"


def test_filter_by_club():
    results = [
        _result(club="Club A"),
        _result(club="Club B"),
    ]
    filtered = filter_results(results, club="Club A")
    assert len(filtered) == 1
    assert filtered[0].club == "Club A"


def test_filter_by_gender_case_insensitive():
    results = [
        _result(gender="Male"),
        _result(gender="Female"),
    ]
    assert len(filter_results(results, gender="male")) == 1
    assert len(filter_results(results, gender="Female")) == 1


def test_filter_by_name_partial():
    results = [
        _result(athlete_name="Ben Cole"),
        _result(athlete_name="Alice Brown"),
    ]
    filtered = filter_results(results, name="col")
    assert len(filtered) == 1
    assert filtered[0].athlete_name == "Ben Cole"


def test_filter_combined():
    results = [
        _result(athlete_name="Ben Cole", category="V40", gender="Male", club="Club A"),
        _result(
            athlete_name="Jon Davies", category="V40", gender="Male", club="Club B"
        ),
        _result(
            athlete_name="Sue Lane",
            category="Senior Women",
            gender="Female",
            club="Club A",
        ),
    ]
    filtered = filter_results(results, category="V40", club="Club A")
    assert len(filtered) == 1
    assert filtered[0].athlete_name == "Ben Cole"


def test_filter_no_filters_returns_all():
    results = [_result(), _result(position=2)]
    assert filter_results(results) == results


def test_filter_name_empty_string_returns_all():
    results = [_result(), _result(position=2)]
    assert filter_results(results, name="") == results


# ---------------------------------------------------------------------------
# build_csv
# ---------------------------------------------------------------------------


def test_build_csv_headers():
    csv_str, _ = build_csv([], "Men", "Round 1")
    reader = csv.reader(io.StringIO(csv_str))
    headers = next(reader)
    assert "Pos" in headers
    assert "Name" in headers
    assert "Cat Pos" in headers
    assert "Club" in headers


def test_build_csv_rows():
    results = [
        _result(
            position=1,
            athlete_name="Ben Cole",
            time="00:29:27",
            category="V40",
            club="Swindon",
        ),
    ]
    csv_str, _ = build_csv(results, "Men", "Round 1")
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)  # skip header
    row = next(reader)
    assert "1" in row
    assert "Ben Cole" in row
    assert "V40" in row
    assert "Swindon" in row


def test_build_csv_filename():
    _, filename = build_csv([], "Men", "Round 1")
    assert filename.endswith(".csv")
    assert "Men" in filename
    assert "Round" in filename


def test_build_csv_nullable_fields():
    results = [
        _result(
            race_number=None, category_position=None, gender_position=None, club=None
        ),
    ]
    csv_str, _ = build_csv(results, "Men", "Round 1")
    # Should not raise and should produce valid CSV
    reader = csv.reader(io.StringIO(csv_str))
    next(reader)  # header
    row = next(reader)
    assert "" in row  # nullable fields produce empty strings


# ---------------------------------------------------------------------------
# build_pdf
# ---------------------------------------------------------------------------


def test_build_pdf_returns_bytes():
    pdf_bytes, _ = build_pdf([], "Men", "Round 1")
    assert isinstance(pdf_bytes, bytes)


def test_build_pdf_starts_with_pdf_magic():
    pdf_bytes, _ = build_pdf([_result()], "Women", "Round 2")
    assert pdf_bytes[:4] == b"%PDF"


def test_build_pdf_filename():
    _, filename = build_pdf([], "U13", "Round 1")
    assert filename.endswith(".pdf")
    assert "U13" in filename


# ---------------------------------------------------------------------------
# Export routes
# ---------------------------------------------------------------------------


def test_csv_export_route_returns_csv(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Men")
    _make_result(test_db, race.id, athlete_name="Ben Cole")

    resp = test_client.get(f"/results/export/csv?race_id={race.id}")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Ben Cole" in resp.text


def test_csv_export_content_disposition(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Men")

    resp = test_client.get(f"/results/export/csv?race_id={race.id}")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".csv" in cd


def test_csv_export_404_invalid_race(test_client):
    resp = test_client.get("/results/export/csv?race_id=99999")
    assert resp.status_code == 404


def test_pdf_export_route_returns_pdf(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Women")
    _make_result(test_db, race.id)

    resp = test_client.get(f"/results/export/pdf?race_id={race.id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_pdf_export_404_invalid_race(test_client):
    resp = test_client.get("/results/export/pdf?race_id=99999")
    assert resp.status_code == 404


def test_csv_export_with_category_filter(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Men")
    _make_result(test_db, race.id, athlete_name="Ben Cole", category="V40")
    _make_result(
        test_db, race.id, position=2, athlete_name="Jon Davies", category="Senior Men"
    )

    resp = test_client.get(f"/results/export/csv?race_id={race.id}&category=V40")
    assert resp.status_code == 200
    assert "Ben Cole" in resp.text
    assert "Jon Davies" not in resp.text
