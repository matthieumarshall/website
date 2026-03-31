"""Unit tests for results display routes and repository functions."""

import duckdb

from website import repository
from website.models import Race, Result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_season(db: duckdb.DuckDBPyConnection, name: str = "2025"):
    return repository.create_season(db, name)


def _make_fixture(
    db: duckdb.DuckDBPyConnection, season_id: int, title: str = "Round 1"
):
    return repository.create_fixture(
        db,
        season_id=season_id,
        title=title,
        date="2025-10-01",
        location_name="Venue",
        address="1 Test St",
        timetable=[],
        travel_instructions="",
    )


def _make_race(
    db: duckdb.DuckDBPyConnection,
    fixture_id: int,
    name: str = "Men",
    display_order: int = 0,
) -> Race:
    return repository.create_race(
        db, fixture_id=fixture_id, name=name, display_order=display_order
    )


def _make_result(
    db: duckdb.DuckDBPyConnection,
    race_id: int,
    position: int = 1,
    athlete_name: str = "Alice Smith",
    time: str = "00:30:00",
    category: str = "Senior Women",
    gender: str = "Female",
    race_number: int | None = 100,
    category_position: int | None = 1,
    gender_position: int | None = 1,
    club: str | None = "Test AC",
) -> Result:
    return repository.create_result(
        db,
        race_id=race_id,
        position=position,
        athlete_name=athlete_name,
        time=time,
        category=category,
        gender=gender,
        race_number=race_number,
        category_position=category_position,
        gender_position=gender_position,
        club=club,
    )


# ---------------------------------------------------------------------------
# Repository: canonical sort order
# ---------------------------------------------------------------------------


def test_canonical_sort_juniors_first(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    repository.create_race(test_db, fixture.id, "Men")
    repository.create_race(test_db, fixture.id, "U17")
    repository.create_race(test_db, fixture.id, "U9")
    repository.create_race(test_db, fixture.id, "Women")
    repository.create_race(test_db, fixture.id, "U13")

    races = repository.list_races_for_fixture(test_db, fixture.id)
    names = [r.name for r in races]
    # Juniors should come first, sorted by age group; adults alphabetically after
    assert names.index("U9") < names.index("U13")
    assert names.index("U13") < names.index("U17")
    assert names.index("U17") < names.index("Men")
    assert names.index("Men") < names.index("Women")


def test_canonical_sort_adults_alphabetical(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    repository.create_race(test_db, fixture.id, "Women")
    repository.create_race(test_db, fixture.id, "Men")

    races = repository.list_races_for_fixture(test_db, fixture.id)
    names = [r.name for r in races]
    assert names == ["Men", "Women"]


# ---------------------------------------------------------------------------
# Repository: list_results_for_race
# ---------------------------------------------------------------------------


def test_list_results_for_race_ordered_by_position(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id)

    _make_result(test_db, race.id, position=3, athlete_name="Charlie")
    _make_result(test_db, race.id, position=1, athlete_name="Alpha")
    _make_result(test_db, race.id, position=2, athlete_name="Bravo")

    results = repository.list_results_for_race(test_db, race.id)
    assert [r.position for r in results] == [1, 2, 3]
    assert results[0].athlete_name == "Alpha"


def test_list_results_for_race_empty(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id)
    assert repository.list_results_for_race(test_db, race.id) == []


# ---------------------------------------------------------------------------
# Repository: fixture_has_results
# ---------------------------------------------------------------------------


def test_fixture_has_results_false_when_no_results(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    _make_race(test_db, fixture.id)
    assert repository.fixture_has_results(test_db, fixture.id) is False


def test_fixture_has_results_true_when_results_exist(
    test_db: duckdb.DuckDBPyConnection,
):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id)
    _make_result(test_db, race.id)
    assert repository.fixture_has_results(test_db, fixture.id) is True


# ---------------------------------------------------------------------------
# Repository: get_race_by_id
# ---------------------------------------------------------------------------


def test_get_race_by_id_found(test_db: duckdb.DuckDBPyConnection):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="U11")
    fetched = repository.get_race_by_id(test_db, race.id)
    assert fetched is not None
    assert fetched.name == "U11"


def test_get_race_by_id_not_found(test_db: duckdb.DuckDBPyConnection):
    assert repository.get_race_by_id(test_db, 99999) is None


# ---------------------------------------------------------------------------
# Routes: /results
# ---------------------------------------------------------------------------


def test_results_page_no_seasons(test_client):
    resp = test_client.get("/results")
    assert resp.status_code == 200
    assert "Results" in resp.text


def test_results_page_with_data(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Men")
    _make_result(test_db, race.id, athlete_name="Ben Cole")

    resp = test_client.get(
        f"/results?season_id={season.id}&fixture_id={fixture.id}&race_id={race.id}"
    )
    assert resp.status_code == 200
    assert "Ben Cole" in resp.text


def test_results_page_defaults_to_first_season(test_client, test_db):
    season = _make_season(test_db, "2025")
    _make_fixture(test_db, season.id)
    resp = test_client.get("/results")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Routes: HTMX partials
# ---------------------------------------------------------------------------


def test_results_fixture_panel_returns_html(test_client, test_db):
    season = _make_season(test_db)
    _make_fixture(test_db, season.id, title="Round 1")
    resp = test_client.get(f"/results/fixture-panel?season_id={season.id}")
    assert resp.status_code == 200
    assert "Round 1" in resp.text


def test_results_race_panel_returns_html(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    _make_race(test_db, fixture.id, name="Women")
    resp = test_client.get(
        f"/results/race-panel?fixture_id={fixture.id}&season_id={season.id}"
    )
    assert resp.status_code == 200
    assert "Women" in resp.text


def test_results_race_panel_404_unknown_fixture(test_client):
    resp = test_client.get("/results/race-panel?fixture_id=99999")
    assert resp.status_code == 404


def test_results_race_table_returns_html(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id, name="Men")
    _make_result(test_db, race.id, athlete_name="Jon Davies")
    resp = test_client.get(f"/results/race-table?race_id={race.id}")
    assert resp.status_code == 200
    assert "Jon Davies" in resp.text


def test_results_race_table_404_unknown_race(test_client):
    resp = test_client.get("/results/race-table?race_id=99999")
    assert resp.status_code == 404


def test_results_race_table_empty_state(test_client, test_db):
    season = _make_season(test_db)
    fixture = _make_fixture(test_db, season.id)
    race = _make_race(test_db, fixture.id)
    resp = test_client.get(f"/results/race-table?race_id={race.id}")
    assert resp.status_code == 200
    assert "No results available" in resp.text
