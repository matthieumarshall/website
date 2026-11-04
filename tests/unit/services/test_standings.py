"""Standings: score key resolution, recalculation and the standings tables."""

from datetime import date, datetime

import duckdb
import pytest

from website import repository
from website.errors import NotFoundError, OperationFailedError
from website.models import Fixture
from website.services.results import ResultsService
from website.services.standings import StandingsService, scores_by_fixture


def _fixture(fixture_id: int) -> Fixture:
    return Fixture(
        id=fixture_id,
        season_id=1,
        title=f"Round {fixture_id}",
        date=date(2025, 10, 1),
        location_name="Park",
        address="Somewhere",
        timetable=[],
        travel_instructions="",
        created_at=datetime(2025, 1, 1),
    )


class TestScoresByFixture:
    def test_resolves_ids_round_labels_and_positions(self) -> None:
        fixtures = [_fixture(10), _fixture(20), _fixture(30)]
        raw = '{"10": 4, "r2": 7, "3": 9, "junk": 1, "r9": 2}'
        assert scores_by_fixture(raw, fixtures) == {"10": 4, "20": 7, "30": 9}

    def test_explicit_fixture_id_wins_over_positional_key(self) -> None:
        fixtures = [_fixture(10), _fixture(20)]
        assert scores_by_fixture('{"20": 1, "r2": 5}', fixtures) == {"20": 1}

    @pytest.mark.parametrize("raw", ["", "not json", "[1, 2]"])
    def test_invalid_json_yields_no_scores(self, raw: str) -> None:
        assert scores_by_fixture(raw, [_fixture(1)]) == {}


def _seed_results(db: duckdb.DuckDBPyConnection) -> int:
    season = repository.create_season(db, "2025-26")
    for round_number, day in enumerate(("2025-10-05", "2025-11-09"), start=1):
        fixture = repository.create_fixture(
            db, season.id, f"Round {round_number}", day, "Park", "Addr", [], ""
        )
        race = repository.create_race(db, fixture.id, "Men")
        for position, name in enumerate(("Ann", "Ben", "Cat"), start=1):
            repository.create_result(
                db,
                race_id=race.id,
                position=position,
                athlete_name=name,
                time=f"00:3{position}:00",
                category="SM",
                gender="M",
                club="Oxford AC",
            )
    return season.id


class TestRecalculate:
    def test_recalculation_writes_standings_and_tables_resolve_scores(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season_id = _seed_results(test_db)
        service = StandingsService(test_db)
        service.recalculate(season_id)

        overview = service.overview(season_id)
        individual = [c for c in overview.categories if c.type == "individual"]
        assert individual, "recalculation should produce individual standings"
        category = individual[0].category
        standings_type = "individual"
        table = service.table(season_id, category, standings_type)
        assert table.rows
        assert len(table.fixtures) == 2
        fixture_ids = {str(f.id) for f in table.fixtures}
        for row in table.rows:
            assert set(row.scores_by_fixture) <= fixture_ids

        team_fixture = repository.list_fixtures_for_season(test_db, season_id)[0]
        round_results = repository.list_team_round_results_for_fixture(
            test_db, team_fixture.id, "Men"
        )
        assert len(round_results) == 1
        assert round_results[0].position == 1
        assert round_results[0].score > 0
        assert round_results[0].scoring_members == [
            "Ann (1)",
            "Ben (2)",
            "Cat (3)",
        ]

        team_table = service.table(season_id, "Men", "team")
        assert team_table.team_round_results
        assert team_table.team_round_results[0].fixture_id == team_fixture.id

        panel = ResultsService(test_db).race_panel(team_fixture.id)
        assert panel.team_round_results == round_results

    def test_round_results_rank_teams_within_the_fixture(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2025-26")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-10-05", "Park", "Addr", [], ""
        )
        race = repository.create_race(test_db, fixture.id, "Men")
        for position, (name, club) in enumerate(
            [
                ("A Runner", "Fast AC"),
                ("B Runner", "Fast AC"),
                ("C Runner", "Fast AC"),
                ("D Runner", "Slow AC"),
                ("E Runner", "Slow AC"),
                ("F Runner", "Slow AC"),
            ],
            start=1,
        ):
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

        StandingsService(test_db).recalculate(season.id)

        round_results = repository.list_team_round_results_for_fixture(
            test_db, fixture.id, "Men"
        )
        assert [result.position for result in round_results] == [1, 2]
        assert [result.team_name for result in round_results] == [
            "Fast AC A",
            "Slow AC A",
        ]
        assert round_results[0].score < round_results[1].score
        assert round_results[0].scoring_members == [
            "A Runner (1)",
            "B Runner (2)",
            "C Runner (3)",
        ]

    def test_recalculate_unknown_season(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(NotFoundError):
            StandingsService(test_db).recalculate(999)

    def test_calculator_failure_is_reported(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Broken")

        def explode(_db: duckdb.DuckDBPyConnection, _season_id: int) -> None:
            raise RuntimeError("boom")

        with pytest.raises(OperationFailedError, match="boom"):
            StandingsService(test_db, recalculator=explode).recalculate(season.id)

    def test_season_without_fixtures_is_a_no_op(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "Empty")
        StandingsService(test_db).recalculate(season.id)
        assert not repository.season_has_standings(test_db, season.id)
