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

import json
import logging
from datetime import timedelta
from pathlib import Path

import duckdb

from pyresults import (
    CompetitionConfig,
    DomainRaceResult,
    IndividualScoreService,
    InMemoryRaceResultRepository,
    InMemoryScoreRepository,
    InMemoryTeamResultRepository,
    TeamScoreService,
    TeamScoringService,
    build_default_config,
)

from website import repository

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def recalculate_standings(db: duckdb.DuckDBPyConnection, season_id: int) -> None:
    """Recalculate and persist standings for *season_id*.

    Steps:
    1. Load all results from DuckDB for the season (fixtures ordered by date).
    2. Build pyresults domain objects in-memory; no filesystem access.
    3. Run IndividualScoreService and TeamScoreService.
    4. Persist results to individual_standings / team_standings tables.

    Rows with ``is_imported = true`` are left untouched; this function only
    writes rows for the current season's calculated standings.

    Args:
        db: Active DuckDB connection.
        season_id: Primary key of the season to recalculate.
    """
    fixtures = repository.list_fixtures_for_season(db, season_id)
    if not fixtures:
        _logger.info("Season %s has no fixtures; nothing to calculate.", season_id)
        return

    # Assign round numbers by fixture date order (r1 = earliest, r2 = next, …)
    # This is the canonical mapping; it must stay consistent across calls.
    round_for_fixture: dict[int, str] = {
        f.id: f"r{i + 1}" for i, f in enumerate(fixtures)
    }
    round_numbers = [f"r{i + 1}" for i in range(len(fixtures))]

    # Build in-memory repositories
    race_result_repo = InMemoryRaceResultRepository()
    individual_score_repo = InMemoryScoreRepository()
    team_result_repo = InMemoryTeamResultRepository()
    team_score_repo = InMemoryScoreRepository()

    # Build config with dynamic round_numbers for this season
    config = _build_season_config(round_numbers)

    team_scoring_service = TeamScoringService(config=config)

    # Populate race result repo and team result repo from DuckDB
    for fixture in fixtures:
        round_number = round_for_fixture[fixture.id]
        races = repository.list_races_for_fixture(db, fixture.id)

        for race in races:
            results = repository.list_results_for_race(db, race.id)
            if not results:
                continue

            race_result = DomainRaceResult(
                race_name=race.name,
                round_number=round_number,
            )
            for r in results:
                from pyresults import Athlete

                athlete = Athlete(
                    name=r.athlete_name,
                    club=r.club or "",
                    race_number=str(r.race_number) if r.race_number is not None else "",
                    position=r.position,
                    time=_parse_time(r.time),
                    gender=r.gender,
                    category=r.category,
                )
                race_result.add_athlete(athlete)

            race_result_repo.save_race_result(race_result)

            # Pre-calculate per-round team results for each category
            team_categories = team_scoring_service.get_team_categories_for_race(
                race.name
            )
            for category_code in team_categories:
                try:
                    category = config.category_config.get_category(category_code)
                    teams = team_scoring_service.calculate_teams_for_race(
                        race_result, category
                    )
                    if category.team_size is None:
                        continue
                    if category_code in ["Men", "Women"]:
                        penalty_score = len(race_result.athletes) + 1
                    else:
                        penalty_score = (
                            len(race_result.get_athletes_by_category(category_code)) + 1
                        )
                    result_data = team_scoring_service.create_team_result_data(
                        teams, category.team_size, penalty_score
                    )
                    team_result_repo.save_team_results(
                        category_code, round_number, result_data
                    )
                except ValueError as exc:
                    _logger.warning(
                        "Could not calculate teams for %s in round %s: %s",
                        category_code,
                        round_number,
                        exc,
                    )

    # Run individual scoring
    individual_svc = IndividualScoreService(
        config=config,
        race_result_repo=race_result_repo,
        score_repo=individual_score_repo,
    )
    individual_svc.update_all_categories()

    # Run team scoring
    team_svc = TeamScoreService(
        config=config,
        race_result_repo=race_result_repo,
        team_result_repo=team_result_repo,
        team_score_repo=team_score_repo,
        team_scoring_service=team_scoring_service,
    )
    team_svc.update_all_team_categories()

    # Persist results — delete existing calculated rows first, then insert new
    _save_individual_standings(
        db, season_id, individual_score_repo, round_for_fixture, fixtures
    )
    _save_team_standings(db, season_id, team_score_repo, round_for_fixture, fixtures)

    _logger.info(
        "Standings recalculated for season %s (%d fixtures).",
        season_id,
        len(fixtures),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_season_config(round_numbers: list[str]) -> CompetitionConfig:
    """Return a CompetitionConfig with season-specific round numbers.

    All other settings (categories, divisions, mappings) come from the
    default OXL config.  data_base_path is set to a dummy value since only
    in-memory repositories are used.
    """
    base = build_default_config()
    base.round_numbers = round_numbers
    base.data_base_path = Path("/dev/null")  # never accessed; in-memory only
    return base


def _parse_time(time_str: str) -> timedelta:
    """Parse a time string into a timedelta.

    Accepts a number of common formats:
    - "0 days 00:29:27"  (pandas timedelta repr)
    - "00:29:27"
    - "29:27"
    Returns timedelta(0) if unparseable.
    """
    # Strip "N days " prefix from pandas timedelta strings
    if " days " in time_str:
        time_str = time_str.split(" days ")[-1]
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(float(parts[2]))
            return timedelta(hours=h, minutes=m, seconds=s)
        if len(parts) == 2:
            m, s = int(parts[0]), int(float(parts[1]))
            return timedelta(minutes=m, seconds=s)
    except (ValueError, IndexError):
        pass
    return timedelta()


def _round_number_to_fixture_id(
    round_number: str, round_for_fixture: dict[int, str]
) -> int | None:
    """Return the fixture_id for a given round_number, or None."""
    for fid, rn in round_for_fixture.items():
        if rn == round_number:
            return fid
    return None


def _save_individual_standings(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    score_repo: InMemoryScoreRepository,
    round_for_fixture: dict[int, str],
    fixtures,
) -> None:
    """Write individual standings to DuckDB, preserving is_imported rows."""
    # Delete only rows that were calculated (not imported) for this season
    db.execute(
        "DELETE FROM individual_standings WHERE season_id = ? AND is_imported = false",
        [season_id],
    )

    all_scores = score_repo.all_scores()
    if not all_scores:
        return

    rows = []
    for category, scores in all_scores.items():
        for pos, score in enumerate(scores, start=1):
            # Build per-fixture score JSON using fixture_id keys
            fixture_scores: dict[str, int] = {}
            for round_number, pts in score.round_scores.items():
                fid = _round_number_to_fixture_id(round_number, round_for_fixture)
                if fid is not None:
                    fixture_scores[str(fid)] = pts

            rounds_competed = len(score.round_scores)
            # Use the same counting logic as IndividualScoreService
            rounds_to_count = (
                max(1, rounds_competed - 1) if rounds_competed > 1 else rounds_competed
            )
            total = score.calculate_total_score(rounds_to_count)
            if total > 99999:
                total = 999999

            rows.append(
                (
                    season_id,
                    category,
                    pos,
                    score.name,
                    score.club,
                    total,
                    rounds_competed,
                    json.dumps(fixture_scores),
                    False,  # is_imported
                )
            )

    if rows:
        db.executemany(
            "INSERT INTO individual_standings"
            " (season_id, category, position, athlete_name, club,"
            "  total_score, rounds_competed, fixture_scores, is_imported)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    _logger.debug(
        "Saved %d individual standing rows for season %s.", len(rows), season_id
    )


def _save_team_standings(
    db: duckdb.DuckDBPyConnection,
    season_id: int,
    score_repo: InMemoryScoreRepository,
    round_for_fixture: dict[int, str],
    fixtures,
) -> None:
    """Write team standings to DuckDB, preserving is_imported rows."""
    db.execute(
        "DELETE FROM team_standings WHERE season_id = ? AND is_imported = false",
        [season_id],
    )

    all_scores = score_repo.all_scores()
    if not all_scores:
        return

    rows = []
    for category, scores in all_scores.items():
        for pos, score in enumerate(scores, start=1):
            fixture_scores: dict[str, int] = {}
            for round_number, pts in score.round_scores.items():
                fid = _round_number_to_fixture_id(round_number, round_for_fixture)
                if fid is not None:
                    fixture_scores[str(fid)] = pts

            rounds_competed = len(score.round_scores)
            total = score.calculate_total_score(rounds_competed)  # all rounds for teams
            if total > 99999:
                total = 999999

            # Parse team label from name (e.g. "Oxford City AC A" → label="A")
            team_name = score.name
            team_label: str | None = None
            club: str | None = None
            parts = team_name.rsplit(" ", 1)
            if len(parts) == 2 and len(parts[1]) == 1 and parts[1].isupper():
                club = parts[0]
                team_label = parts[1]
            else:
                club = team_name

            rows.append(
                (
                    season_id,
                    category,
                    pos,
                    team_name,
                    club,
                    team_label,
                    total,
                    rounds_competed,
                    json.dumps(fixture_scores),
                    False,  # is_imported
                )
            )

    if rows:
        db.executemany(
            "INSERT INTO team_standings"
            " (season_id, category, position, team_name, club, team_label,"
            "  total_score, rounds_competed, fixture_scores, is_imported)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    _logger.debug("Saved %d team standing rows for season %s.", len(rows), season_id)
