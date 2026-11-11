"""Route tests for manual race CSV uploads and race setup."""

import io
import re

import duckdb
import pytest
from fastapi.testclient import TestClient

from website import repository
from website.models.fixtures import TimetableEntry
from website.services.standings import StandingsService

_CSV_HEADER = "Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club\n"


@pytest.fixture
def race_upload_fixture(test_db: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    season = repository.create_season(test_db, "2025-2026")
    fixture = repository.create_fixture(
        test_db,
        season_id=season.id,
        title="Round 5",
        date="2026-03-01",
        location_name="Henley Showground",
        address="Henley",
        timetable=[TimetableEntry(time="11:00", event="Under 11 Girls Race")],
        travel_instructions="",
    )
    return season.id, fixture.id


def _csrf(client: TestClient) -> str:
    response = client.get("/fixtures")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    assert match, "No CSRF token found"
    return match.group(1)


def _csv_file(name: str = "Uploaded Runner"):
    content = (
        _CSV_HEADER + f"1,101,{name},00:30:00,Senior Men,1,Male,1,Oxford City AC\n"
    )
    return ("results.csv", io.BytesIO(content.encode()), "text/csv")


def test_junior_team_results_hide_divisions_and_export_penalties(
    admin_client, test_db, race_upload_fixture
):
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "U11 Boys & Girls")
    repository.create_result(
        test_db, race.id, 1, "Junior", "00:10:00", "U11B", "M", club="Oxford"
    )
    StandingsService(test_db).recalculate(season_id)
    params = {"fixture_id": fixture_id, "category": "U11B"}
    page = admin_client.get("/results/team-table", params=params)
    csv = admin_client.get("/results/team-export/csv", params=params)
    pdf = admin_client.get("/results/team-export/pdf", params=params)
    assert page.status_code == csv.status_code == pdf.status_code == 200
    assert "Division" not in page.text
    assert "scoring-runner-list" in page.text
    assert page.text.count("Penalty (2)") == 2
    assert "Division" not in csv.text
    assert csv.text.count("Penalty (2)") == 2
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.parametrize(
    ("race_name", "senior", "under23", "gender"),
    [
        ("Senior Men", "SM", "U23M", "M"),
        ("Senior Women", "SW", "U23 Women", "F"),
        ("Senior Women", "Senior Women", "U23W", "F"),
    ],
)
def test_individual_results_combine_u23_with_seniors(
    admin_client, test_db, race_upload_fixture, race_name, senior, under23, gender
):
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, race_name)
    for position, name, category, club in (
        (1, "Young Runner", under23, "AC"),
        (2, "Guest Runner", under23, "Guest"),
        (3, "Senior Runner", senior, "AC"),
    ):
        repository.create_result(
            test_db,
            race.id,
            position,
            name,
            "00:30:00",
            category,
            gender,
            category_position=1,
            club=club,
        )
    page = admin_client.get(
        "/results",
        params={"season_id": season_id, "fixture_id": fixture_id, "race_id": race.id},
    )
    partial = admin_client.get("/results/race-table", params={"race_id": race.id})
    csv = admin_client.get(
        "/results/export/csv", params={"race_id": race.id, "category": senior}
    )
    pdf = admin_client.get(
        "/results/export/pdf", params={"race_id": race.id, "category": senior}
    )
    assert (
        page.status_code
        == partial.status_code
        == csv.status_code
        == pdf.status_code
        == 200
    )
    for html in (page.text, partial.text):
        assert f'data-category="{senior}"' in html
        assert under23 not in html
    assert "Young Runner" in csv.text and "Senior Runner" in csv.text
    assert under23 not in csv.text
    alternate = "SW" if gender == "F" else "Senior Men"
    assert (
        "Young Runner"
        in admin_client.get(
            "/results/export/csv", params={"race_id": race.id, "category": alternate}
        ).text
    )
    from website.services.results import ResultsService

    rows = ResultsService(test_db).race_results(race.id)[1]
    assert [row.category_position for row in rows] == [1, None, 2]
    assert repository.list_results_for_race(test_db, race.id)[0].category == under23


def test_race_creation_still_offers_manual_csv(
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    _, fixture_id = race_upload_fixture
    response = admin_client.post(
        f"/fixtures/{fixture_id}/races",
        data={"csrf_token": _csrf(admin_client), "race_name": "Under 11 Girls"},
    )

    assert response.status_code == 200
    assert "Race added. Upload its results below." in response.text
    assert "Upload and Replace Results" in response.text
    assert "RaceTec" not in response.text
    race = repository.list_races_for_fixture(test_db, fixture_id)[0]
    assert f"/fixtures/{fixture_id}/race/{race.id}/upload-csv" in response.text


def test_both_fixture_and_results_pages_render_per_race_upload(
    admin_client: TestClient,
    race_upload_fixture: tuple[int, int],
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Senior Men")

    fixture_page = admin_client.get(f"/fixtures?season_id={season_id}")
    results_page = admin_client.get(
        f"/results?season_id={season_id}&fixture_id={fixture_id}&race_id={race.id}"
    )

    upload_action = f"/fixtures/{fixture_id}/race/{race.id}/upload-csv"
    assert fixture_page.status_code == results_page.status_code == 200
    assert upload_action in fixture_page.text
    assert upload_action in results_page.text
    assert 'name="return_to" value="results"' in results_page.text


def test_fixture_upload_replaces_only_the_selected_race(
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Senior Men")
    other_race = repository.create_race(test_db, fixture_id, "Senior Women")
    repository.create_result(
        test_db, race.id, 1, "Previous Runner", "00:31:00", "SM", "Male"
    )
    repository.create_result(
        test_db, other_race.id, 1, "Unaffected Runner", "00:32:00", "SW", "Female"
    )

    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/upload-csv",
        data={
            "csrf_token": _csrf(admin_client),
            "return_to": "fixtures",
            "season_id": str(season_id),
        },
        files={"csv_file": _csv_file("Latest Runner")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Imported 1 results. Protected manual results were kept." in response.text
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Latest Runner"]
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, other_race.id)
    ] == ["Unaffected Runner"]


def test_results_page_upload_returns_updated_race_panel(
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Men")

    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/upload-csv",
        data={
            "csrf_token": _csrf(admin_client),
            "return_to": "results",
            "season_id": str(season_id),
        },
        files={"csv_file": _csv_file()},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Uploaded Runner" in response.text
    assert "Imported 1 results. Protected manual results were kept." in response.text
    assert "Individual Results" in response.text
    assert "Team Results" in response.text
    assert "Team scores for Round 5" not in response.text
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Uploaded Runner"]


def test_team_round_scores_render_on_results_and_standings_pages(
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Men")
    runners = [
        ("A Runner", "Oxford City AC"),
        ("B Runner", "Oxford City AC"),
        ("C Runner", "Oxford City AC"),
        ("D Runner", "Witney AC"),
        ("E Runner", "Witney AC"),
        ("F Runner", "Witney AC"),
    ]
    for position, (name, club) in enumerate(runners, start=1):
        repository.create_result(
            test_db,
            race_id=race.id,
            position=position,
            athlete_name=name,
            time=f"00:3{position}:00",
            category="SM",
            gender="M",
            club=club,
        )
    StandingsService(test_db).recalculate(season_id)
    test_db.execute(
        "INSERT INTO team_round_results "
        "(fixture_id, category, position, team_name, club, team_label, score, scoring_members) "
        "VALUES (?, 'Women', 1, 'Women Team A', 'Women Team', 'A', 6, '[]')",
        [fixture_id],
    )

    results_response = admin_client.get(
        f"/results?season_id={season_id}&fixture_id={fixture_id}&race_id={race.id}"
    )
    team_response = admin_client.get(
        f"/results?season_id={season_id}&fixture_id={fixture_id}"
        f"&race_id={race.id}&view_mode=team"
    )
    fixture_panel_response = admin_client.get(
        f"/results/fixture-panel?season_id={season_id}&view_mode=team"
    )
    standings_response = admin_client.get(
        f"/standings/table?season_id={season_id}&category=Men&standings_type=team"
    )

    assert (
        results_response.status_code
        == team_response.status_code
        == fixture_panel_response.status_code
        == standings_response.status_code
        == 200
    )
    assert "Individual Results" in results_response.text
    assert "Team scores for Round 5" not in results_response.text
    assert 'id="results-filter"' in results_response.text
    assert 'id="results-view-mode"' in team_response.text
    assert 'name="view_mode"' in team_response.text
    assert 'value="team"' in team_response.text
    assert 'hx-include="#results-view-mode"' in fixture_panel_response.text
    assert "Team scores for Round 5" in team_response.text
    assert "Oxford City AC A" in team_response.text
    assert "A Runner (1)" in team_response.text
    assert 'aria-label="Team results for Men"' in team_response.text
    assert 'aria-label="Team results for Women"' in team_response.text
    assert "Women Team A" not in team_response.text
    women_response = admin_client.get(
        f"/results/team-table?fixture_id={fixture_id}&category=Women"
    )
    assert "Women Team A" in women_response.text
    assert "Oxford City AC A" not in women_response.text
    assert "category=Women" in women_response.text
    women_csv = admin_client.get(
        f"/results/team-export/csv?fixture_id={fixture_id}&category=Women"
    )
    assert "Women Team A" in women_csv.text
    assert "Oxford City AC A" not in women_csv.text
    assert 'id="results-filter"' not in team_response.text
    assert "Scoring runners" in standings_response.text
    assert "Pos 1" in standings_response.text
    assert "A Runner (1)" in standings_response.text
    team_csv = admin_client.get(
        f"/results/team-export/csv?fixture_id={fixture_id}&division=3"
    )
    assert team_csv.status_code == 200
    assert "Category,Pos,Division,Team,Score,Scoring runners" in team_csv.text
    assert "Oxford City AC A" in team_csv.text
    assert (
        "Oxford City AC A"
        not in admin_client.get(
            f"/results/team-export/csv?fixture_id={fixture_id}&division=1"
        ).text
    )
    standings_csv = admin_client.get(
        f"/standings/export/csv?season_id={season_id}&category=Men&standings_type=team&division=3"
    )
    assert "Division" in standings_csv.text
    assert "Oxford City AC A" in standings_csv.text


def test_invalid_upload_preserves_results(
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Senior Men")
    repository.create_result(
        test_db, race.id, 1, "Existing Runner", "00:31:00", "SM", "Male"
    )

    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/upload-csv",
        data={
            "csrf_token": _csrf(admin_client),
            "return_to": "fixtures",
            "season_id": str(season_id),
        },
        files={
            "csv_file": ("invalid.csv", b"Name,Time\nRunner,00:30:00\n", "text/csv")
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "The CSV must include Pos and Name columns." in response.text
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Existing Runner"]

    full_page_response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/upload-csv",
        data={
            "csrf_token": _csrf(admin_client),
            "return_to": "fixtures",
            "season_id": str(season_id),
        },
        files={
            "csv_file": ("invalid.csv", b"Name,Time\nRunner,00:30:00\n", "text/csv")
        },
    )
    assert full_page_response.status_code == 422
    assert "The CSV must include Pos and Name columns." in full_page_response.text
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Existing Runner"]


def test_upload_requires_staff_and_csrf(
    test_client: TestClient,
    admin_client: TestClient,
    test_db: duckdb.DuckDBPyConnection,
    race_upload_fixture: tuple[int, int],
) -> None:
    _, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Senior Men")
    url = f"/fixtures/{fixture_id}/race/{race.id}/upload-csv"
    files = {"csv_file": _csv_file()}

    anonymous_response = test_client.post(
        url,
        data={"csrf_token": "invalid", "return_to": "fixtures"},
        files=files,
        follow_redirects=False,
    )
    csrf_response = admin_client.post(
        url,
        data={"return_to": "fixtures"},
        files={"csv_file": _csv_file()},
        follow_redirects=False,
    )

    assert anonymous_response.status_code in (302, 403)
    assert csrf_response.status_code in (403, 422)


def test_upload_warns_about_single_name_but_imports(
    admin_client: TestClient, test_db: duckdb.DuckDBPyConnection, race_upload_fixture
):
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Men")
    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/upload-csv",
        data={
            "csrf_token": _csrf(admin_client),
            "return_to": "results",
            "season_id": str(season_id),
        },
        files={"csv_file": _csv_file("Madonna")},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Names may be incomplete: Madonna" in response.text
    assert (
        repository.list_results_for_race(test_db, race.id)[0].athlete_name == "Madonna"
    )


def test_results_panel_direct_requests_render_full_page(
    admin_client: TestClient, test_db: duckdb.DuckDBPyConnection, race_upload_fixture
):
    season_id, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Men")
    url = (
        f"/results/race-panel?fixture_id={fixture_id}&race_id={race.id}&view_mode=team"
    )
    page = admin_client.get(url)
    assert page.status_code == 200
    assert "<html" in page.text
    assert 'id="results-view-mode"' in page.text
    assert 'value="team"' in page.text
    assert "results-filter.js" in page.text
    fragment = admin_client.get(url, headers={"HX-Request": "true"})
    assert "<html" not in fragment.text
    season_page = admin_client.get(
        f"/results/fixture-panel?season_id={season_id}&view_mode=team"
    )
    assert "<html" in season_page.text
    assert 'value="team"' in season_page.text


def test_staff_can_add_and_edit_protected_result(
    admin_client, test_db, race_upload_fixture
):
    _, fixture_id = race_upload_fixture
    race = repository.create_race(test_db, fixture_id, "Senior Men")
    form = {
        "csrf_token": _csrf(admin_client),
        "position": "1",
        "athlete_name": "Runner One",
        "time": "00:30:00",
        "category": "SM",
        "gender": "Male",
        "club": "Oxford AC",
    }
    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/results",
        data=form,
        follow_redirects=False,
    )
    assert response.status_code == 303
    result = repository.list_results_for_race(test_db, race.id)[0]
    assert result.is_locked
    form.update(
        athlete_name="Corrected Runner",
        race_number="",
        category_position="",
        gender_position="",
    )
    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/results/{result.id}/edit",
        data=form,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        repository.list_results_for_race(test_db, race.id)[0].athlete_name
        == "Corrected Runner"
    )


def test_manual_result_routes_enforce_round_ownership_and_delete(
    admin_client, test_db, race_upload_fixture
):
    _, fixture_id = race_upload_fixture
    other = repository.create_fixture(
        test_db, race_upload_fixture[0], "Other", "2026-04-01", "V", "A", [], ""
    )
    race = repository.create_race(test_db, fixture_id, "Men")
    result = repository.create_result(
        test_db, race.id, 1, "Runner", "30:00", "SM", "M", club="AC"
    )
    token = _csrf(admin_client)
    wrong = admin_client.post(
        f"/fixtures/{other.id}/race/{race.id}/results/{result.id}/delete",
        data={"csrf_token": token},
    )
    assert wrong.status_code == 404
    assert repository.get_result_by_id(test_db, result.id) is not None
    response = admin_client.post(
        f"/fixtures/{fixture_id}/race/{race.id}/results/{result.id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert repository.get_result_by_id(test_db, result.id) is None
