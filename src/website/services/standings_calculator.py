"""Standings calculation bridge between the website's DuckDB data and pyresults.

This module is the integration point between the two systems:

  Website database (DuckDB)
      └─ results / races / fixtures
            ↓  build domain objects in-memory
  pyresults scoring services
      └─ IndividualScoreService + TeamScoreService
            ↓  read computed Score objects
  Website database (DuckDB)
      └─ individual_standings / team_standings

Convention: fixtures sorted by date within a season become r1, r2, r3, …
This mapping is the source of truth for all standings calculations.
"""

import logging
import re
from datetime import timedelta
from pathlib import Path

from pyresults import (
    Athlete,
    CategoryType,
    CompetitionConfig,
    DomainRaceResult,
    Gender,
    IndividualScoreService,
    InMemoryRaceResultRepository,
    InMemoryScoreRepository,
    InMemoryTeamResultRepository,
    TeamScoreService,
    TeamScoringService,
    build_default_config,
)

from website import repository
from website.db import Connection
from website.errors import NotFoundError
from website.models import (
    CalculatedIndividualStanding,
    CalculatedTeamRoundResult,
    CalculatedTeamStanding,
    Fixture,
    Result,
)
from website.services.standings_categories import (
    add_oxl_categories,
    scoring_category,
    team_race_name,
)

_logger = logging.getLogger(__name__)
_MAX_TOTAL = 99999
_CAPPED_TOTAL = 999999
_TIME_PARTS_HMS = 3
_TIME_PARTS_MS = 2
_OPEN_CATEGORIES = ("Men", "Women")


class _Scorers:
    """The in-memory pyresults repositories and services for one season."""

    def __init__(self, config: CompetitionConfig) -> None:
        self.config = config
        self.race_results = InMemoryRaceResultRepository()
        self.individual_scores = InMemoryScoreRepository()
        self.team_results = InMemoryTeamResultRepository()
        self.team_scores = InMemoryScoreRepository()
        self.team_scoring = TeamScoringService(config=config)
        self.team_round_results: list[CalculatedTeamRoundResult] = []
        self.team_penalties: dict[str, dict[str, int]] = {}

    def run(self) -> None:
        IndividualScoreService(
            config=self.config,
            race_result_repo=self.race_results,
            score_repo=self.individual_scores,
        ).update_all_categories()
        team_service = TeamScoreService(
            config=self.config,
            race_result_repo=self.race_results,
            team_result_repo=self.team_results,
            team_score_repo=self.team_scores,
            team_scoring_service=self.team_scoring,
        )
        for category in self.config.category_config.get_categories_by_type(
            CategoryType.TEAM
        ):
            try:
                team_service.update_team_scores_for_category(category.code)
            except ValueError as exc:
                _logger.warning(
                    "Could not update team scores for %s: %s", category.code, exc
                )


def recalculate_standings(db: Connection, season_id: int) -> None:
    """Recalculate and persist standings for *season_id*.

    Loads the season's results (fixtures ordered by date), scores them with
    pyresults entirely in memory, then replaces the calculated standings rows.
    Rows with ``is_imported = true`` are left untouched.
    """
    season = repository.get_season_by_id(db, season_id)
    if season is None:
        raise NotFoundError(f"Season {season_id} not found")
    fixtures = repository.list_fixtures_for_season(db, season_id)
    if not fixtures:
        _logger.info("Season %s has no fixtures; nothing to calculate.", season_id)
        return

    # r1 = earliest fixture, r2 = next, …; must stay consistent across calls.
    round_for_fixture = {f.id: f"r{i + 1}" for i, f in enumerate(fixtures)}
    scorers = _Scorers(_build_season_config(list(round_for_fixture.values())))
    for fixture in fixtures:
        _load_fixture(db, scorers, fixture, round_for_fixture[fixture.id], season.name)
    scorers.run()

    fixture_for_round = {rn: fid for fid, rn in round_for_fixture.items()}
    _complete_missing_a_team_results(scorers, fixture_for_round)
    repository.replace_calculated_individual_standings(
        db, season_id, _individual_rows(scorers, fixture_for_round)
    )
    repository.replace_calculated_team_standings(
        db,
        season_id,
        _team_rows(scorers.team_scores, fixture_for_round, scorers.team_penalties),
    )
    repository.replace_calculated_team_round_results(
        db, season_id, scorers.team_round_results
    )
    _logger.info(
        "Standings recalculated for season %s (%d fixtures).", season_id, len(fixtures)
    )


def _complete_missing_a_team_results(
    scorers: _Scorers, fixture_for_round: dict[str, int]
) -> None:
    """Include absent A teams in each scored round's team results."""
    results = scorers.team_round_results
    existing = {(row.fixture_id, row.category, row.team_name) for row in results}
    for category, scores in scorers.team_scores.all_scores().items():
        team_size = scorers.config.category_config.get_category(category).team_size
        if team_size is None:
            continue
        for score in scores:
            club, label = _split_team_name(score.name)
            if label != "A":
                continue
            for round_number, total in scorers.team_penalties.get(category, {}).items():
                fixture_id = fixture_for_round[round_number]
                if (fixture_id, category, score.name) in existing:
                    continue
                results.append(
                    CalculatedTeamRoundResult(
                        fixture_id=fixture_id,
                        category=category,
                        position=1,
                        team_name=score.name,
                        club=club,
                        team_label=label,
                        score=total,
                        scoring_members=[f"Penalty ({total // team_size})"] * team_size,
                    )
                )
    groups: dict[tuple[int, str], list[CalculatedTeamRoundResult]] = {}
    for result in results:
        groups.setdefault((result.fixture_id, result.category), []).append(result)
    scorers.team_round_results = [
        row.model_copy(update={"position": position})
        for group in groups.values()
        for position, row in enumerate(sorted(group, key=lambda row: row.score), 1)
    ]


def _load_fixture(
    db: Connection,
    scorers: _Scorers,
    fixture: Fixture,
    round_number: str,
    season_name: str,
) -> None:
    grouped: dict[str, list[Result]] = {}
    for race in repository.list_races_for_fixture(db, fixture.id):
        race_name = team_race_name(race.name)
        results = [
            result
            for result in repository.list_results_for_race(db, race.id)
            if _eligible_result(scorers.config, race.name, result, season_name)
        ]
        if results:
            grouped.setdefault(race_name, []).extend(results)
    for race_name, results in grouped.items():
        race_result = DomainRaceResult(race_name=race_name, round_number=round_number)
        for position, result in enumerate(sorted(results, key=lambda r: r.position), 1):
            race_result.add_athlete(
                Athlete(
                    name=result.athlete_name,
                    club=result.club or "",
                    race_number=(
                        str(result.race_number)
                        if result.race_number is not None
                        else ""
                    ),
                    position=position,
                    time=_parse_time(result.time),
                    gender=result.gender,
                    category=scoring_category(result.category, season_name),
                )
            )
        scorers.race_results.save_race_result(race_result)
        _save_round_team_results(scorers, fixture.id, race_result, round_number)


def _eligible_result(
    config: CompetitionConfig, race_name: str, result: Result, season_name: str
) -> bool:
    """Only score non-guests in the race assigned to their category."""
    if (result.club or "").strip().casefold() == "guest":
        return False
    category = config.category_config.categories.get(
        scoring_category(result.category, season_name)
    )
    if category is None or category.race_name != team_race_name(race_name):
        return False
    male = bool(re.search(r"\b(?:boys|men)\b", race_name, re.IGNORECASE))
    female = bool(re.search(r"\b(?:girls|women)\b", race_name, re.IGNORECASE))
    return male == female or category.gender == (Gender.MALE if male else Gender.FEMALE)


def _save_round_team_results(
    scorers: _Scorers,
    fixture_id: int,
    race_result: DomainRaceResult,
    round_number: str,
) -> None:
    """Pre-calculate per-round team results for each team category of a race."""
    service = scorers.team_scoring
    for category_code in service.get_team_categories_for_race(race_result.race_name):
        try:
            category = scorers.config.category_config.get_category(category_code)
            teams = service.calculate_teams_for_race(race_result, category)
            if category.team_size is None:
                continue
            if category_code in _OPEN_CATEGORIES:
                penalty_score = len(race_result.athletes) + 1
            else:
                penalty_score = (
                    len(race_result.get_athletes_by_category(category_code)) + 1
                )
            if penalty_score > 1:
                scorers.team_penalties.setdefault(category_code, {})[round_number] = (
                    penalty_score * category.team_size
                )
            result_data = service.create_team_result_data(
                teams, category.team_size, penalty_score
            )
            scorers.team_results.save_team_results(
                category_code, round_number, result_data
            )
            for row in result_data:
                team_name = str(row["Team"])
                club, team_label = _split_team_name(team_name)
                scoring_members = [
                    str(row[f"Runner{index}"])
                    for index in range(1, category.team_size + 1)
                    if row.get(f"Runner{index}")
                ]
                scoring_members.extend(
                    [f"Penalty ({penalty_score})"]
                    * (category.team_size - len(scoring_members))
                )
                scorers.team_round_results.append(
                    CalculatedTeamRoundResult(
                        fixture_id=fixture_id,
                        category=category_code,
                        position=int(row["Pos"]),
                        team_name=team_name,
                        club=club,
                        team_label=team_label,
                        score=int(row["Score"]),
                        scoring_members=scoring_members,
                    )
                )
        except ValueError as exc:
            _logger.warning(
                "Could not calculate teams for %s in round %s: %s",
                category_code,
                round_number,
                exc,
            )


def _build_season_config(round_numbers: list[str]) -> CompetitionConfig:
    """Return the default OXL config with season-specific round numbers.

    ``data_base_path`` is a dummy value since only in-memory repositories are
    used.
    """
    base = build_default_config()
    add_oxl_categories(base)
    base.round_numbers = round_numbers
    base.data_base_path = Path("/dev/null")  # never accessed; in-memory only
    return base


def _parse_time(time_str: str) -> timedelta:
    """Parse "0 days 00:29:27", "00:29:27" or "29:27"; timedelta(0) if invalid."""
    if " days " in time_str:
        time_str = time_str.rsplit(" days ", maxsplit=1)[-1]
    parts = time_str.strip().split(":")
    try:
        if len(parts) == _TIME_PARTS_HMS:
            h, m, s = int(parts[0]), int(parts[1]), int(float(parts[2]))
            return timedelta(hours=h, minutes=m, seconds=s)
        if len(parts) == _TIME_PARTS_MS:
            m, s = int(parts[0]), int(float(parts[1]))
            return timedelta(minutes=m, seconds=s)
    except (ValueError, IndexError):
        pass
    return timedelta()


def _fixture_scores(
    round_scores: dict[str, int], fixture_for_round: dict[str, int]
) -> dict[str, int]:
    return {
        str(fixture_for_round[round_number]): points
        for round_number, points in round_scores.items()
        if round_number in fixture_for_round
    }


def _capped(total: int) -> int:
    return _CAPPED_TOTAL if total > _MAX_TOTAL else total


def _individual_rows(
    scorers: _Scorers, fixture_for_round: dict[str, int]
) -> list[CalculatedIndividualStanding]:
    rows: list[CalculatedIndividualStanding] = []
    for category, scores in scorers.individual_scores.all_scores().items():
        race_name = scorers.config.category_config.get_category(category).race_name
        rounds_held = sum(
            scorers.race_results.exists(race_name, round_number)
            for round_number in scorers.config.round_numbers
        )
        rounds_to_count = max(1, rounds_held - 1)
        # Preserve the library's order for equal totals, including its tie breaks.
        ranked_scores = sorted(
            scores,
            key=lambda score: (
                len(score.round_scores) < rounds_to_count,
                sum(sorted(score.round_scores.values())[:rounds_to_count]),
            ),
        )
        for position, score in enumerate(ranked_scores, start=1):
            rounds_competed = len(score.round_scores)
            rows.append(
                CalculatedIndividualStanding(
                    category=category,
                    position=position,
                    athlete_name=score.name,
                    club=score.club,
                    total_score=_capped(
                        sum(sorted(score.round_scores.values())[:rounds_to_count])
                    ),
                    rounds_competed=rounds_competed,
                    fixture_scores=_fixture_scores(
                        score.round_scores, fixture_for_round
                    ),
                )
            )
    return rows


def _split_team_name(team_name: str) -> tuple[str, str | None]:
    """Split "Oxford City AC A" into ("Oxford City AC", "A")."""
    parts = team_name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) == 1 and parts[1].isupper():  # noqa: PLR2004
        return parts[0], parts[1]
    return team_name, None


def _team_rows(
    score_repo: InMemoryScoreRepository,
    fixture_for_round: dict[str, int],
    penalties: dict[str, dict[str, int]],
) -> list[CalculatedTeamStanding]:
    rows: list[CalculatedTeamStanding] = []
    for category, scores in score_repo.all_scores().items():
        filled_scores = [
            (
                score,
                {
                    **(
                        penalties.get(category, {})
                        if _split_team_name(score.name)[1] == "A"
                        else {}
                    ),
                    **score.round_scores,
                },
            )
            for score in scores
        ]
        filled_scores.sort(
            key=lambda item: (sum(item[1].values()), -len(item[0].round_scores))
        )
        for position, (score, round_scores) in enumerate(filled_scores, start=1):
            rounds_competed = len(score.round_scores)
            club, team_label = _split_team_name(score.name)
            rows.append(
                CalculatedTeamStanding(
                    category=category,
                    position=position,
                    team_name=score.name,
                    club=club,
                    team_label=team_label,
                    # Teams count every round.
                    total_score=_capped(sum(round_scores.values())),
                    rounds_competed=rounds_competed,
                    fixture_scores=_fixture_scores(round_scores, fixture_for_round),
                )
            )
    return rows
