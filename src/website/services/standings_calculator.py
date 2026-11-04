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
    Category,
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
from website.models import (
    CalculatedIndividualStanding,
    CalculatedTeamRoundResult,
    CalculatedTeamStanding,
    Fixture,
    Race,
    Result,
)

_logger = logging.getLogger(__name__)
_MAX_TOTAL = 99999
_CAPPED_TOTAL = 999999
_TIME_PARTS_HMS = 3
_TIME_PARTS_MS = 2
_OPEN_CATEGORIES = ("Men", "Women")
_JUNIOR_TEAM_SIZE = 3
_PRODUCTION_JUNIOR_TEAM_CATEGORIES = (
    (
        "U10B",
        "Under 10 Boys",
        Gender.MALE,
        "U10",
        ("U10B", "U10 Boys", "Under 10 Boys"),
    ),
    (
        "U10G",
        "Under 10 Girls",
        Gender.FEMALE,
        "U10",
        ("U10G", "U10 Girls", "Under 10 Girls"),
    ),
    (
        "U12B",
        "Under 12 Boys",
        Gender.MALE,
        "U12",
        ("U12B", "U12 Boys", "Under 12 Boys"),
    ),
    (
        "U12G",
        "Under 12 Girls",
        Gender.FEMALE,
        "U12",
        ("U12G", "U12 Girls", "Under 12 Girls"),
    ),
    (
        "U14B",
        "Under 14 Boys",
        Gender.MALE,
        "U14",
        ("U14B", "U14 Boys", "Under 14 Boys"),
    ),
    (
        "U14G",
        "Under 14 Girls",
        Gender.FEMALE,
        "U14",
        ("U14G", "U14 Girls", "Under 14 Girls"),
    ),
    (
        "U16B",
        "Under 16 Boys",
        Gender.MALE,
        "U16",
        ("U16B", "U16 Boys", "Under 16 Boys"),
    ),
    (
        "U16G",
        "Under 16 Girls",
        Gender.FEMALE,
        "U16",
        ("U16G", "U16 Girls", "Under 16 Girls"),
    ),
    (
        "U18M",
        "Under 18 Men",
        Gender.MALE,
        "U18",
        ("U18M", "U18 Boys", "U18 Men", "Under 18 Boys", "Under 18 Men"),
    ),
    (
        "U18W",
        "Under 18 Women",
        Gender.FEMALE,
        "U18",
        ("U18W", "U18 Girls", "U18 Women", "Under 18 Girls", "Under 18 Women"),
    ),
)
_PRODUCTION_CATEGORY_ALIASES: dict[str, str] = {
    alias.casefold(): code
    for code, _, _, _, aliases in _PRODUCTION_JUNIOR_TEAM_CATEGORIES
    for alias in aliases
}
_PRODUCTION_RACE_ALIASES = {
    "u20/senior/masters men": "Men",
    "u20/senior/masters women": "Women",
}


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

    def run(self) -> None:
        IndividualScoreService(
            config=self.config,
            race_result_repo=self.race_results,
            score_repo=self.individual_scores,
        ).update_all_categories()
        TeamScoreService(
            config=self.config,
            race_result_repo=self.race_results,
            team_result_repo=self.team_results,
            team_score_repo=self.team_scores,
            team_scoring_service=self.team_scoring,
        ).update_all_team_categories()


def recalculate_standings(db: Connection, season_id: int) -> None:
    """Recalculate and persist standings for *season_id*.

    Loads the season's results (fixtures ordered by date), scores them with
    pyresults entirely in memory, then replaces the calculated standings rows.
    Rows with ``is_imported = true`` are left untouched.
    """
    fixtures = repository.list_fixtures_for_season(db, season_id)
    if not fixtures:
        _logger.info("Season %s has no fixtures; nothing to calculate.", season_id)
        return

    # r1 = earliest fixture, r2 = next, …; must stay consistent across calls.
    round_for_fixture = {f.id: f"r{i + 1}" for i, f in enumerate(fixtures)}
    scorers = _Scorers(_build_season_config(list(round_for_fixture.values())))
    for fixture in fixtures:
        _load_fixture(db, scorers, fixture, round_for_fixture[fixture.id])
    scorers.run()

    fixture_for_round = {rn: fid for fid, rn in round_for_fixture.items()}
    repository.replace_calculated_individual_standings(
        db, season_id, _individual_rows(scorers.individual_scores, fixture_for_round)
    )
    repository.replace_calculated_team_standings(
        db, season_id, _team_rows(scorers.team_scores, fixture_for_round)
    )
    repository.replace_calculated_team_round_results(
        db, season_id, scorers.team_round_results
    )
    _logger.info(
        "Standings recalculated for season %s (%d fixtures).", season_id, len(fixtures)
    )


def _load_fixture(
    db: Connection, scorers: _Scorers, fixture: Fixture, round_number: str
) -> None:
    for race in repository.list_races_for_fixture(db, fixture.id):
        results = repository.list_results_for_race(db, race.id)
        if results:
            _load_race(scorers, fixture.id, race, results, round_number)


def _load_race(
    scorers: _Scorers,
    fixture_id: int,
    race: Race,
    results: list[Result],
    round_number: str,
) -> None:
    race_result = DomainRaceResult(race_name=race.name, round_number=round_number)
    for result in results:
        race_result.add_athlete(
            Athlete(
                name=result.athlete_name,
                club=result.club or "",
                race_number=(
                    str(result.race_number) if result.race_number is not None else ""
                ),
                position=result.position,
                time=_parse_time(result.time),
                gender=result.gender,
                category=_scoring_category(result.category),
            )
        )
    scorers.race_results.save_race_result(race_result)
    _save_round_team_results(scorers, fixture_id, race, race_result, round_number)


def _save_round_team_results(
    scorers: _Scorers,
    fixture_id: int,
    race: Race,
    race_result: DomainRaceResult,
    round_number: str,
) -> None:
    """Pre-calculate per-round team results for each team category of a race."""
    service = scorers.team_scoring
    team_race_name = _canonical_team_race_name(race.name)
    for category_code in service.get_team_categories_for_race(team_race_name):
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
    for code, name, gender, race_name, _ in _PRODUCTION_JUNIOR_TEAM_CATEGORIES:
        base.category_config.categories.setdefault(
            code,
            Category(
                code=code,
                name=name,
                category_type=CategoryType.TEAM,
                gender=gender,
                race_name=race_name,
                team_size=_JUNIOR_TEAM_SIZE,
                age_group=race_name,
            ),
        )
    base.round_numbers = round_numbers
    base.data_base_path = Path("/dev/null")  # never accessed; in-memory only
    return base


def _scoring_category(category: str) -> str:
    """Canonicalise production junior category labels for team scoring."""
    stripped = category.strip()
    return _PRODUCTION_CATEGORY_ALIASES.get(stripped.casefold(), stripped)


def _canonical_team_race_name(race_name: str) -> str:
    """Map production event titles to the scorer's category race names."""
    normalized = re.sub(r"\s*/\s*", "/", " ".join(race_name.casefold().split()))
    if normalized in _PRODUCTION_RACE_ALIASES:
        return _PRODUCTION_RACE_ALIASES[normalized]
    age_group = re.fullmatch(r"u(\d+)(?:\s+boys\s*(?:&|and)\s*girls)?", normalized)
    if age_group:
        return f"U{age_group.group(1)}"
    return race_name.strip()


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
    score_repo: InMemoryScoreRepository, fixture_for_round: dict[str, int]
) -> list[CalculatedIndividualStanding]:
    rows: list[CalculatedIndividualStanding] = []
    for category, scores in score_repo.all_scores().items():
        for position, score in enumerate(scores, start=1):
            rounds_competed = len(score.round_scores)
            # Same counting rule as IndividualScoreService: drop the worst round.
            rounds_to_count = (
                max(1, rounds_competed - 1) if rounds_competed > 1 else rounds_competed
            )
            rows.append(
                CalculatedIndividualStanding(
                    category=category,
                    position=position,
                    athlete_name=score.name,
                    club=score.club,
                    total_score=_capped(score.calculate_total_score(rounds_to_count)),
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
    score_repo: InMemoryScoreRepository, fixture_for_round: dict[str, int]
) -> list[CalculatedTeamStanding]:
    rows: list[CalculatedTeamStanding] = []
    for category, scores in score_repo.all_scores().items():
        for position, score in enumerate(scores, start=1):
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
                    total_score=_capped(score.calculate_total_score(rounds_competed)),
                    rounds_competed=rounds_competed,
                    fixture_scores=_fixture_scores(
                        score.round_scores, fixture_for_round
                    ),
                )
            )
    return rows
