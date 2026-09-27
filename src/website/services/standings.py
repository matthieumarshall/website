"""Standings browsing and recalculation."""

import json
import logging
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import OperationFailedError
from website.models import (
    Fixture,
    IndividualStanding,
    Season,
    StandingCategory,
    TeamStanding,
)
from website.models.standings import ScoreValue
from website.services._common import found
from website.services.standings_calculator import recalculate_standings

_logger = logging.getLogger(__name__)

StandingRow = IndividualStanding | TeamStanding
Recalculator = Callable[[Connection, int], None]


class StandingsOverview(BaseModel):
    """The season selector and category list on the standings page."""

    model_config = ConfigDict(frozen=True)

    seasons: list[Season]
    selected_season: Season | None
    categories: list[StandingCategory]


class StandingsTable(BaseModel):
    """One category's standings with per-fixture scores resolved."""

    model_config = ConfigDict(frozen=True)

    season: Season
    category: str
    standings_type: str
    rows: list[StandingRow]
    fixtures: list[Fixture]


def _parse_scores(raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fixture_id_for_index(index: int, fixtures: Sequence[Fixture]) -> str | None:
    return str(fixtures[index].id) if 0 <= index < len(fixtures) else None


def scores_by_fixture(
    raw_scores: str, fixtures: Sequence[Fixture]
) -> dict[str, ScoreValue]:
    """Map stored score keys to fixture ids.

    Keys may already be fixture ids, round labels (``"r1"``) or 1-based
    fixture positions (``"1"``); anything else is ignored.
    """
    fixture_ids = {str(f.id) for f in fixtures}
    resolved: dict[str, ScoreValue] = {}
    for raw_key, value in _parse_scores(raw_scores).items():
        if not isinstance(value, int | float | str):
            continue
        key = str(raw_key).strip()
        if key in fixture_ids:
            resolved[key] = value
            continue
        normalized = key.lower()
        if normalized.startswith("r") and normalized[1:].isdigit():
            fixture_id = _fixture_id_for_index(int(normalized[1:]) - 1, fixtures)
        elif key.isdigit():
            fixture_id = _fixture_id_for_index(int(key) - 1, fixtures)
        else:
            fixture_id = None
        if fixture_id is not None and fixture_id not in resolved:
            resolved[fixture_id] = value
    return resolved


class StandingsService:
    """Standings pages and the staff-only recalculation."""

    def __init__(
        self, db: Connection, recalculator: Recalculator = recalculate_standings
    ) -> None:
        """Bind the service to a database and a standings calculator."""
        self._db = db
        self._recalculate = recalculator

    def _categories(
        self, season_id: int | None
    ) -> tuple[Season | None, list[StandingCategory]]:
        if season_id is None:
            return None, []
        season = repository.get_season_by_id(self._db, season_id)
        if season is None:
            return None, []
        return season, repository.list_standing_categories(self._db, season_id)

    def overview(self, season_id: int | None) -> StandingsOverview:
        """Return seasons plus the categories of *season_id* (default: latest)."""
        seasons = repository.list_seasons(self._db)
        if season_id is None and seasons:
            season_id = seasons[0].id
        selected_season, categories = self._categories(season_id)
        return StandingsOverview(
            seasons=seasons, selected_season=selected_season, categories=categories
        )

    def category_panel(self, season_id: int | None) -> StandingsOverview:
        """Return the categories of *season_id* only (no default season)."""
        selected_season, categories = self._categories(season_id)
        return StandingsOverview(
            seasons=[], selected_season=selected_season, categories=categories
        )

    def table(
        self, season_id: int, category: str, standings_type: str
    ) -> StandingsTable:
        """Return one category's standings table.

        Raises:
            NotFoundError: If the season does not exist.
        """
        season = found(
            repository.get_season_by_id(self._db, season_id), "Season not found"
        )
        fixtures = repository.list_fixtures_for_season(self._db, season_id)
        loaded: Sequence[StandingRow]
        if standings_type == "team":
            loaded = repository.load_team_standings(self._db, season_id, category)
        else:
            loaded = repository.load_individual_standings(self._db, season_id, category)
        rows: list[StandingRow] = [
            row.model_copy(
                update={
                    "scores_by_fixture": scores_by_fixture(row.fixture_scores, fixtures)
                }
            )
            for row in loaded
        ]
        return StandingsTable(
            season=season,
            category=category,
            standings_type=standings_type,
            rows=rows,
            fixtures=fixtures,
        )

    def recalculate(self, season_id: int) -> None:
        """Recalculate a season's standings from its race results.

        Raises:
            NotFoundError: If the season does not exist.
            OperationFailedError: If the calculation fails.
        """
        found(repository.get_season_by_id(self._db, season_id), "Season not found")
        try:
            self._recalculate(self._db, season_id)
        except Exception as exc:  # third-party scoring can fail in many ways
            _logger.exception("Error recalculating standings for season %s", season_id)
            raise OperationFailedError(f"Standings calculation failed: {exc}") from exc
