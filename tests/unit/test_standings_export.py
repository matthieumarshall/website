"""Unit tests for standings CSV and PDF exports and their routes."""

import csv
import io
import json
from datetime import date, datetime

import duckdb
from fastapi.testclient import TestClient

from website.export import build_standings_csv, build_standings_pdf
from website.models import Fixture, IndividualStanding, TeamStanding
from website.models.standings import ScoreValue


def _fixture(fixture_id: int) -> Fixture:
    return Fixture(
        id=fixture_id,
        season_id=1,
        title=f"Round {fixture_id}",
        date=date(2025, 1, 1),
        location_name="Venue",
        address="Address",
        timetable=[],
        travel_instructions="",
        created_at=datetime(2025, 1, 1),
    )


def _individual(
    position: int, name: str, scores: dict[str, ScoreValue]
) -> IndividualStanding:
    return IndividualStanding(
        id=position,
        season_id=1,
        category="Senior Women",
        position=position,
        athlete_name=name,
        club="Oxford City AC",
        total_score=sum(int(v) for v in scores.values()),
        rounds_competed=len(scores),
        fixture_scores=json.dumps(scores),
        is_imported=False,
        scores_by_fixture=scores,
    )


def _team() -> TeamStanding:
    return TeamStanding(
        id=1,
        season_id=1,
        category="Senior Men",
        position=1,
        team_name="Oxford City A",
        team_label="A",
        club="Oxford City AC",
        total_score=120,
        rounds_competed=2,
        fixture_scores="{}",
        is_imported=False,
        scores_by_fixture={"1": 60, "2": 60},
    )


def test_csv_matches_on_screen_columns() -> None:
    fixtures = [_fixture(1), _fixture(2)]
    rows = [
        _individual(1, "Alice Smith", {"1": 3, "2": 5}),
        _individual(2, "Bea Jones", {"2": 7}),
    ]
    text, filename = build_standings_csv(
        rows, fixtures, "2024-2025", "Senior Women", "individual"
    )
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == ["Pos", "Name", "Club", "R1", "R2", "Total", "Rds"]
    assert parsed[1] == ["1", "Alice Smith", "Oxford City AC", "3", "5", "8", "2"]
    assert parsed[2] == ["2", "Bea Jones", "Oxford City AC", "", "7", "7", "1"]
    assert filename == "2024-2025_Senior Women_individual.csv"


def test_csv_team_standings_use_team_name() -> None:
    text, filename = build_standings_csv(
        [_team()], [_fixture(1), _fixture(2)], "2024-2025", "Senior Men", "team"
    )
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0][1] == "Team"
    assert parsed[1][:3] == ["1", "Oxford City A", "Oxford City AC"]
    assert filename.endswith("_team.csv")


def test_csv_filename_is_sanitised() -> None:
    _, filename = build_standings_csv([], [], "2024/25", 'U13 "Girls"', "individual")
    assert "/" not in filename
    assert '"' not in filename


def test_pdf_is_valid_with_many_rounds_and_none() -> None:
    many = [_fixture(i) for i in range(1, 13)]
    rows = [_individual(1, "Alice Smith", {str(i): i for i in range(1, 13)})]
    for fixtures in (many, []):
        data, filename = build_standings_pdf(
            rows, fixtures, "2024-2025", "Senior Women", "individual"
        )
        assert data.startswith(b"%PDF")
        assert filename == "2024-2025_Senior Women_individual.pdf"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _seed(db: duckdb.DuckDBPyConnection) -> int:
    db.execute("INSERT INTO seasons (name) VALUES (?)", ["2024-2025"])
    row = db.execute("SELECT id FROM seasons WHERE name = ?", ["2024-2025"]).fetchone()
    assert row is not None
    season_id = row[0]
    db.execute(
        "INSERT INTO fixtures (season_id, title, date, location_name, address)"
        " VALUES (?, ?, ?, ?, ?)",
        [season_id, "R1", "2025-01-01", "Test Venue", "Test Address"],
    )
    db.execute(
        "INSERT INTO individual_standings "
        "(season_id, category, position, athlete_name, club, "
        " total_score, rounds_competed, fixture_scores, is_imported) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, false)",
        [
            season_id,
            "Senior Women",
            1,
            "Alice Smith",
            "Oxford City AC",
            23,
            1,
            json.dumps({"r1": 23}),
        ],
    )
    return season_id


def _params(season_id: int) -> dict[str, object]:
    return {
        "season_id": season_id,
        "category": "Senior Women",
        "standings_type": "individual",
    }


def test_csv_route(test_client: TestClient, test_db: duckdb.DuckDBPyConnection) -> None:
    season_id = _seed(test_db)
    resp = test_client.get("/standings/export/csv", params=_params(season_id))
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert ".csv" in resp.headers["content-disposition"]
    parsed = list(csv.reader(io.StringIO(resp.text)))
    assert parsed[1] == ["1", "Alice Smith", "Oxford City AC", "23", "23", "1"]


def test_pdf_route(test_client: TestClient, test_db: duckdb.DuckDBPyConnection) -> None:
    season_id = _seed(test_db)
    resp = test_client.get("/standings/export/pdf", params=_params(season_id))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_export_unknown_season_is_404(test_client: TestClient) -> None:
    for fmt in ("csv", "pdf"):
        resp = test_client.get(f"/standings/export/{fmt}", params=_params(99999))
        assert resp.status_code == 404


def test_table_shows_export_links(
    test_client: TestClient, test_db: duckdb.DuckDBPyConnection
) -> None:
    season_id = _seed(test_db)
    resp = test_client.get("/standings/table", params=_params(season_id))
    query = f"season_id={season_id}&amp;category=Senior%20Women&amp;standings_type=individual"
    assert f"/standings/export/csv?{query}" in resp.text
    assert f"/standings/export/pdf?{query}" in resp.text
