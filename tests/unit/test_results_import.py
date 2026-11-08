"""Tests for manual CSV parsing and race-result replacement."""

import duckdb
import pytest

from website import repository
from website.errors import ConflictError, NotFoundError, ValidationError
from website.services.results_import import (
    ResultsImportService,
    normalise_category,
    parse_csv_results,
)

_CSV_HEADER = "Pos,Race No,Name,Time,Category,Cat Pos,Gender,Gen Pos,Club\n"


def _create_fixture(db: duckdb.DuckDBPyConnection, season_name: str = "2025-2026"):
    season = repository.create_season(db, season_name)
    fixture = repository.create_fixture(
        db,
        season_id=season.id,
        title="Round 5",
        date="2026-03-01",
        location_name="Henley Showground",
        address="Henley",
        timetable=[],
        travel_instructions="",
    )
    return season, fixture


def test_normalise_category() -> None:
    assert normalise_category("Senior Men", "Male") == "SM"
    assert normalise_category("U9 Girls", "Female") == "U9G"
    assert normalise_category("V40", "Male") == "MV40"
    assert normalise_category("SuperVeteran", "Male") == "SuperVeteran"


def test_parse_existing_csv_format_sorts_finishers() -> None:
    csv_text = (
        _CSV_HEADER
        + "2,102,Runner Two,00:31:00,Senior Men,2,Male,2,Oxford City AC\n"
        + "1,101,Runner One,00:30:00,Senior Men,1,Male,1,Oxford City AC\n"
    )

    parsed = parse_csv_results(csv_text)

    assert [result.position for result in parsed] == [1, 2]
    assert parsed[0].race_number == 101
    assert parsed[0].athlete_name == "Runner One"


@pytest.mark.parametrize(
    "csv_text",
    ["", "Name,Time\nRunner,00:30:00\n", _CSV_HEADER],
)
def test_parse_rejects_csv_without_valid_results(csv_text: str) -> None:
    with pytest.raises(ValidationError):
        parse_csv_results(csv_text)


def test_create_race_validates_fixture_name_and_duplicates(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    _, fixture = _create_fixture(test_db)
    service = ResultsImportService(test_db)

    with pytest.raises(NotFoundError):
        service.create_race(9999, "Race")
    with pytest.raises(ValidationError):
        service.create_race(fixture.id, " ")

    race = service.create_race(fixture.id, "Under 11 Girls")
    assert race.name == "Under 11 Girls"
    with pytest.raises(ConflictError):
        service.create_race(fixture.id, " UNDER 11 GIRLS ")


def test_latest_valid_csv_replaces_only_that_race(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    _, fixture = _create_fixture(test_db)
    target = repository.create_race(test_db, fixture.id, "Senior Men")
    other = repository.create_race(test_db, fixture.id, "Senior Women")
    repository.create_result(
        test_db, target.id, 1, "Previous Runner", "00:30:00", "SM", "Male"
    )
    repository.create_result(
        test_db, other.id, 1, "Unaffected Runner", "00:31:00", "SW", "Female"
    )
    service = ResultsImportService(test_db)

    first_upload = (
        _CSV_HEADER + "1,101,First Upload,00:29:00,Senior Men,1,Male,1,Oxford AC\n"
    )
    latest_upload = (
        _CSV_HEADER + "1,102,Latest Upload,00:28:00,Senior Men,1,Male,1,Oxford AC\n"
    )
    service.ingest_csv(fixture.id, target.id, first_upload)
    summary = service.ingest_csv(fixture.id, target.id, latest_upload)

    assert summary.finishers_imported == 1
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, target.id)
    ] == ["Latest Upload"]
    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, other.id)
    ] == ["Unaffected Runner"]


def test_invalid_csv_preserves_existing_results(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    _, fixture = _create_fixture(test_db)
    race = repository.create_race(test_db, fixture.id, "Senior Men")
    repository.create_result(
        test_db, race.id, 1, "Existing Runner", "00:30:00", "SM", "Male"
    )

    with pytest.raises(ValidationError):
        ResultsImportService(test_db).ingest_csv(
            fixture.id, race.id, "Name,Time\nNew Runner,00:29:00\n"
        )

    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Existing Runner"]


def test_failed_database_replacement_rolls_back_old_results(
    test_db: duckdb.DuckDBPyConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, fixture = _create_fixture(test_db)
    race = repository.create_race(test_db, fixture.id, "Senior Men")
    repository.create_result(
        test_db, race.id, 1, "Existing Runner", "00:31:00", "SM", "Male"
    )

    def fail_insert(*_args, **_kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(repository, "create_results_batch", fail_insert)
    with pytest.raises(RuntimeError, match="insert failed"):
        ResultsImportService(test_db).ingest_csv(
            fixture.id,
            race.id,
            _CSV_HEADER + "1,102,New Runner,00:29:00,Senior Men,1,Male,1,Oxford AC\n",
        )

    assert [
        result.athlete_name
        for result in repository.list_results_for_race(test_db, race.id)
    ] == ["Existing Runner"]


def test_import_rejects_race_from_another_fixture(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    _, fixture = _create_fixture(test_db)
    _, other_fixture = _create_fixture(test_db, "2024-2025")
    race = repository.create_race(test_db, other_fixture.id, "Senior Men")

    with pytest.raises(NotFoundError):
        ResultsImportService(test_db).ingest_csv(
            fixture.id, race.id, _CSV_HEADER + "1,1,Runner,00:30:00,SM,1,Male,1,AC\n"
        )


def test_parse_separate_name_columns_and_combined_names():
    from website.services.results_import import parse_csv_results

    rows = parse_csv_results("Pos,First Name,Last Name\n1,Ada,Lovelace\n2,Grace,Hopper")
    assert [row.athlete_name for row in rows] == ["Ada Lovelace", "Grace Hopper"]
    assert (
        parse_csv_results("Pos,Name\n1,Ada Lovelace")[0].athlete_name == "Ada Lovelace"
    )


def test_parse_firstname_and_surname_headers():
    from website.services.results_import import parse_csv_results

    rows = parse_csv_results("Pos,Firstname,Surname\n1,Ada,Lovelace")
    assert rows[0].athlete_name == "Ada Lovelace"
