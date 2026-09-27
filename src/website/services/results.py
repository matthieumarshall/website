"""Race results browsing, export and source PDF lookup."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import NotFoundError
from website.export import filter_results
from website.models import Fixture, Race, Result, Season
from website.services._common import found


class ResultsBrowser(BaseModel):
    """The season → fixture → race selection shown on the results page."""

    model_config = ConfigDict(frozen=True)

    seasons: list[Season]
    selected_season: Season | None
    fixtures: list[Fixture]
    active_fixture: Fixture | None
    races: list[Race]
    active_race: Race | None
    race_results: list[Result]


class RacePanel(BaseModel):
    """The races of one fixture with one race selected."""

    model_config = ConfigDict(frozen=True)

    active_fixture: Fixture
    races: list[Race]
    active_race: Race | None
    race_results: list[Result]


class ResultsExport(BaseModel):
    """Filtered results of one race, ready to be written as CSV or PDF."""

    model_config = ConfigDict(frozen=True)

    race_name: str
    fixture_title: str
    results: list[Result]


class ResultFilters(BaseModel):
    """Optional filters applied to exported results."""

    model_config = ConfigDict(frozen=True)

    category: str | None = None
    club: str | None = None
    gender: str | None = None
    name: str | None = None


class ResultsService:
    """Read-only access to results, defaulting selections to the first item."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def browse(
        self,
        season_id: int | None = None,
        fixture_id: int | None = None,
        race_id: int | None = None,
    ) -> ResultsBrowser:
        """Resolve the selected season, fixture and race (latest/first by default)."""
        db = self._db
        seasons = repository.list_seasons(db)
        if season_id is None and seasons:
            season_id = seasons[0].id
        selected_season = (
            repository.get_season_by_id(db, season_id)
            if season_id is not None
            else None
        )
        fixtures = (
            repository.list_fixtures_for_season(db, selected_season.id)
            if selected_season
            else []
        )
        if fixture_id is None and fixtures:
            fixture_id = fixtures[0].id
        active_fixture = (
            repository.get_fixture_by_id(db, fixture_id)
            if fixture_id is not None
            else None
        )
        races = (
            repository.list_races_for_fixture(db, active_fixture.id)
            if active_fixture
            else []
        )
        if race_id is None and races:
            race_id = races[0].id
        active_race = (
            repository.get_race_by_id(db, race_id) if race_id is not None else None
        )
        return ResultsBrowser(
            seasons=seasons,
            selected_season=selected_season,
            fixtures=fixtures,
            active_fixture=active_fixture,
            races=races,
            active_race=active_race,
            race_results=(
                repository.list_results_for_race(db, active_race.id)
                if active_race
                else []
            ),
        )

    def race_panel(self, fixture_id: int, race_id: int | None = None) -> RacePanel:
        """Return a fixture's races with *race_id* (or the first race) selected.

        Raises:
            NotFoundError: If the fixture does not exist.
        """
        db = self._db
        fixture = found(
            repository.get_fixture_by_id(db, fixture_id), "Fixture not found"
        )
        races = repository.list_races_for_fixture(db, fixture_id)
        if race_id is not None:
            active_race = repository.get_race_by_id(db, race_id)
        else:
            active_race = races[0] if races else None
        return RacePanel(
            active_fixture=fixture,
            races=races,
            active_race=active_race,
            race_results=(
                repository.list_results_for_race(db, active_race.id)
                if active_race
                else []
            ),
        )

    def race_results(self, race_id: int) -> tuple[Race, list[Result]]:
        """Return a race and its results.

        Raises:
            NotFoundError: If the race does not exist.
        """
        race = found(repository.get_race_by_id(self._db, race_id), "Race not found")
        return race, repository.list_results_for_race(self._db, race_id)

    def export(self, race_id: int, filters: ResultFilters) -> ResultsExport:
        """Return a race's results filtered for export.

        Raises:
            NotFoundError: If the race does not exist.
        """
        race, results = self.race_results(race_id)
        fixture = repository.get_fixture_by_id(self._db, race.fixture_id)
        return ResultsExport(
            race_name=race.name,
            fixture_title=fixture.title if fixture else "Unknown",
            results=filter_results(results, **filters.model_dump()),
        )

    def source_pdf_path(self, fixture_id: int, root: Path) -> Path:
        """Return the original results PDF for a fixture, confined to *root*.

        Raises:
            NotFoundError: If there is no PDF, or its path escapes *root*.
        """
        not_available = "Source PDF not available"
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if fixture is None or not fixture.source_pdf:
            raise NotFoundError(not_available)
        # Defend against path traversal: resolve inside the known root and verify.
        safe_path = (root / fixture.source_pdf).resolve()
        if not safe_path.is_relative_to(root.resolve()) or not safe_path.is_file():
            raise NotFoundError(not_available)
        return safe_path
