"""Standings: score key resolution, recalculation and the standings tables."""

from datetime import date, datetime

import duckdb
import pytest

from website import repository
from website.errors import NotFoundError, OperationFailedError
from website.models import Fixture, IndividualStanding, TeamStanding
from website.services.results import ResultsService
from website.services.standings import StandingsService, scores_by_fixture
from website.services.standings_categories import standing_category_catalog


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


def test_standing_category_catalog_follows_season_format() -> None:
    historical = standing_category_catalog("2025-26")
    current = standing_category_catalog("2026-27")

    historical_categories = {(item.category, item.type) for item in historical}
    current_categories = {(item.category, item.type) for item in current}
    assert ("U9B", "individual") in historical_categories
    assert ("U9B", "team") in historical_categories
    assert ("U10B", "individual") not in historical_categories
    assert ("U10B", "team") not in historical_categories
    assert ("U10B", "individual") in current_categories
    assert ("U10B", "team") in current_categories
    assert ("U9B", "individual") not in current_categories
    assert ("U9B", "team") not in current_categories
    assert not any(category.startswith("U23") for category, _ in current_categories)
    assert any(item.category == "M35" for item in current)
    assert any(item.category == "WV70" for item in current)


def test_standings_overview_includes_empty_configured_categories(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    season = repository.create_season(test_db, "2026-27")

    categories = StandingsService(test_db).overview(season.id).categories

    assert any(
        item.category == "U10B" and item.type == "individual" and item.count == 0
        for item in categories
    )
    assert any(
        item.category == "U10B" and item.type == "team" and item.count == 0
        for item in categories
    )
    assert not any(item.category in {"U23M", "U23W"} for item in categories)


def test_imported_u23_standings_appear_in_senior_table(test_db):
    season = repository.create_season(test_db, "2025-26")
    test_db.execute(
        "INSERT INTO individual_standings (season_id, category, position, athlete_name, club, total_score, rounds_competed, fixture_scores, is_imported) VALUES (?, 'U23M', 1, 'Young Runner', 'AC', 3, 1, '{}', true)",
        [season.id],
    )
    service = StandingsService(test_db)
    categories = service.overview(season.id).categories
    assert (
        next(
            c.count for c in categories if c.category == "SM" and c.type == "individual"
        )
        == 1
    )
    rows = service.table(season.id, "SM", "individual").rows
    assert len(rows) == 1
    assert isinstance(rows[0], IndividualStanding)
    assert (rows[0].athlete_name, rows[0].category) == ("Young Runner", "SM")
    service.recalculate(season.id)
    assert len(service.table(season.id, "SM", "individual").rows) == 1


def test_missing_team_round_gets_runner_penalties(test_db):
    season = repository.create_season(test_db, "2025-26")
    fixtures = []
    for number in (1, 2, 3):
        fixture = repository.create_fixture(
            test_db,
            season.id,
            f"Round {number}",
            f"2025-10-0{number}",
            "Park",
            "",
            [],
            "",
        )
        fixtures.append(fixture)
        if number == 3:
            continue
        race = repository.create_race(test_db, fixture.id, "Men")
        clubs = ["Alpha"] * 7 + (["Beta"] * 7 if number == 1 else [])
        for position, club in enumerate(clubs, 1):
            repository.create_result(
                test_db,
                race.id,
                position,
                f"{club} {number} {position}",
                "00:30:00",
                "SM",
                "M",
                club=club,
            )
    service = StandingsService(test_db)
    service.recalculate(season.id)
    rows = {row.club: row for row in service.table(season.id, "Men", "team").rows}
    assert isinstance(rows["Alpha"], TeamStanding)
    assert isinstance(rows["Beta"], TeamStanding)
    assert rows["Beta"].scores_by_fixture[str(fixtures[1].id)] == 56
    assert str(fixtures[2].id) not in rows["Beta"].scores_by_fixture
    assert rows["Beta"].rounds_competed == 1
    assert rows["Beta"].total_score == 77 + 56
    assert rows["Alpha"].division_position == 1
    assert rows["Beta"].division_position == 2


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


@pytest.mark.parametrize(
    "race_name,category,wrong",
    [
        ("U10 Boys & Girls", "U10B", "U12B"),
        ("U10 Boys", "U10B", "U10G"),
        ("U9 Boys & Girls", "U9B", "U11B"),
        ("Men", "SM", "U10B"),
    ],
)
def test_ineligible_runners_do_not_affect_scoring(test_db, race_name, category, wrong):
    season = repository.create_season(test_db, "2026-27")
    fixture = repository.create_fixture(
        test_db, season.id, "Round 1", "2026-10-04", "Park", "", [], ""
    )
    race = repository.create_race(test_db, fixture.id, race_name)
    for position, (name, cat, club) in enumerate(
        [
            ("Guest Runner", category, "  gUeSt  "),
            ("Wrong Race", wrong, "Other"),
            ("Eligible One", category, "Oxford"),
            ("Eligible Two", category, "Oxford"),
        ],
        1,
    ):
        repository.create_result(
            test_db, race.id, position, name, "00:10:00", cat, "M", club=club
        )

    StandingsService(test_db).recalculate(season.id)
    rows = repository.load_individual_standings(test_db, season.id, category)
    assert {row.athlete_name for row in rows} == {"Eligible One", "Eligible Two"}
    assert [row.total_score for row in rows] == [1, 2]
    team_category = "Men" if race_name == "Men" else category
    team = repository.list_team_round_results_for_fixture(
        test_db, fixture.id, team_category
    )[0]
    assert team.scoring_members[:2] == ["Eligible One (1)", "Eligible Two (2)"]
    assert all(member == "Penalty (3)" for member in team.scoring_members[2:])
    assert team.score == 3 + 3 * (len(team.scoring_members) - 2)
    assert len(repository.list_results_for_race(test_db, race.id)) == 4
    assert not repository.load_individual_standings(test_db, season.id, wrong)


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
        category = next(item.category for item in individual if item.count > 0)
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
            "Penalty (4)",
            "Penalty (4)",
            "Penalty (4)",
            "Penalty (4)",
        ]

        team_table = service.table(season_id, "Men", "team")
        assert team_table.team_round_results
        assert team_table.team_round_results[0].fixture_id == team_fixture.id

        panel = ResultsService(test_db).race_panel(team_fixture.id)
        assert panel.team_round_results[0].team_name == round_results[0].team_name
        assert panel.team_round_results[0].division == 3
        assert panel.team_round_results[0].division_position == 1

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
            "Penalty (7)",
            "Penalty (7)",
            "Penalty (7)",
            "Penalty (7)",
        ]

    def test_historical_odd_junior_bands_keep_individual_and_team_scores(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2025-26")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-10-05", "Park", "Addr", [], ""
        )
        race = repository.create_race(test_db, fixture.id, "U9 Boys & Girls")
        runners = [
            ("Boy One", "U9B", "M"),
            ("Girl One", "U9G", "F"),
            ("Boy Two", "U9B", "M"),
            ("Girl Two", "U9G", "F"),
            ("Boy Three", "U9B", "M"),
            ("Girl Three", "U9G", "F"),
        ]
        for position, (name, category, gender) in enumerate(runners, start=1):
            repository.create_result(
                test_db,
                race_id=race.id,
                position=position,
                athlete_name=name,
                time=f"00:3{position}:00",
                category=category,
                gender=gender,
                club="Oxford AC",
            )

        StandingsService(test_db).recalculate(season.id)

        team_results = repository.list_team_round_results_for_fixture(
            test_db, fixture.id
        )
        assert {result.category for result in team_results} == {"U9B", "U9G"}
        assert len(repository.load_individual_standings(test_db, season.id, "U9B")) == 3

    def test_separate_gendered_races_both_contribute_to_standings(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2025-26")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2025-10-05", "Park", "Addr", [], ""
        )
        for label, category, gender in (("Boys", "U13B", "M"), ("Girls", "U13G", "F")):
            race = repository.create_race(test_db, fixture.id, f"U13 {label}")
            for position in range(1, 4):
                repository.create_result(
                    test_db,
                    race.id,
                    position,
                    f"{label} Runner {position}",
                    "00:10:00",
                    category,
                    gender,
                    club="Oxford AC",
                )
        StandingsService(test_db).recalculate(season.id)
        for category in ("U13B", "U13G"):
            assert (
                len(repository.load_individual_standings(test_db, season.id, category))
                == 3
            )
            assert repository.list_team_round_results_for_fixture(
                test_db, fixture.id, category
            )
            assert repository.load_team_standings(test_db, season.id, category)

    def test_production_race_names_and_category_labels_are_scored(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2026-27")
        fixture = repository.create_fixture(
            test_db, season.id, "Round 1", "2026-10-04", "Park", "Addr", [], ""
        )
        junior_groups = (
            (10, "U10B", "U10 Boys", "U10G", "U10 Girls"),
            (12, "U12B", "U12 Boys", "U12G", "U12 Girls"),
            (14, "U14B", "U14 Boys", "U14G", "U14 Girls"),
            (16, "U16B", "U16 Boys", "U16G", "U16 Girls"),
            (18, "U18M", "U18 Boys", "U18W", "U18 Girls"),
        )
        expected_junior_categories: set[str] = set()
        for age, male_code, male_label, female_code, female_label in junior_groups:
            race = repository.create_race(test_db, fixture.id, f"U{age} Boys & Girls")
            expected_junior_categories.update((male_code, female_code))
            for position in range(1, 7):
                is_male = position % 2 == 1
                member_number = (position + 1) // 2
                code = male_code if is_male else female_code
                label = male_label if is_male else female_label
                category = code if member_number != 2 else label
                gender = "M" if is_male else "F"
                name = f"U{age} {'Boy' if is_male else 'Girl'} {member_number}"
                repository.create_result(
                    test_db,
                    race_id=race.id,
                    position=position,
                    athlete_name=name,
                    time=f"00:3{position}:00",
                    category=category,
                    gender=gender,
                    club="Oxford AC",
                )

        for race_name, category, gender, count, u23_code in (
            ("U20/Senior/Masters Men", "SM", "M", 7, "U23M"),
            ("U20/Senior/Masters Women", "SW", "F", 4, "U23W"),
        ):
            race = repository.create_race(test_db, fixture.id, race_name)
            for position in range(1, count + 1):
                repository.create_result(
                    test_db,
                    race_id=race.id,
                    position=position,
                    athlete_name=f"{race_name} Runner {position}",
                    time=f"00:3{position}:00",
                    category=u23_code if position == 1 else category,
                    gender=gender,
                    club="Oxford AC",
                )

        StandingsService(test_db).recalculate(season.id)

        round_results = repository.list_team_round_results_for_fixture(
            test_db, fixture.id
        )
        members_by_category = {
            result.category: result.scoring_members for result in round_results
        }
        assert set(members_by_category) == expected_junior_categories | {
            "Men",
            "Women",
        }
        assert all(
            len(members_by_category[category]) == 3
            for category in expected_junior_categories
        )
        for category in expected_junior_categories:
            standings = repository.load_team_standings(test_db, season.id, category)
            assert standings, f"No season team standings for {category}"
            assert standings[0].rounds_competed == 1
        assert len(members_by_category["Men"]) == 7
        assert len(members_by_category["Women"]) == 4
        assert members_by_category["U10G"][0] == "U10 Girl 1 (1)"
        senior_men = repository.load_individual_standings(test_db, season.id, "SM")
        senior_women = repository.load_individual_standings(test_db, season.id, "SW")
        assert any(
            row.athlete_name == "U20/Senior/Masters Men Runner 1" for row in senior_men
        )
        assert any(
            row.athlete_name == "U20/Senior/Masters Women Runner 1"
            for row in senior_women
        )

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
