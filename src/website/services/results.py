"""Race results browsing, export and source PDF lookup."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import NotFoundError
from website.export import filter_results
from website.models import Fixture, Race, Result, Season, TeamRoundResult
from website.services._common import found
from website.services.archive import stored_file
from website.services.standings_categories import scoring_category, team_race_name
from website.services.team_divisions import with_divisions

ResultsViewMode = Literal["individual", "team"]


def _present_race_results(race: Race, results: list[Result]) -> list[Result]:
    """Combine U23 and senior results without altering stored race data."""
    categories = [scoring_category(result.category) for result in results]
    combined = {
        category
        for result, category in zip(results, categories, strict=True)
        if category in {"SM", "SW"}
        and result.category.strip().casefold()
        not in {"sm", "sw", "senior men", "senior women"}
    }
    positions: dict[str, int] = {}
    output = []
    for result, category in sorted(
        zip(results, categories, strict=True), key=lambda item: item[0].position
    ):
        if category not in {"SM", "SW"}:
            output.append(result)
            continue
        updates: dict[str, object] = {"category": category}
        if category in combined:
            valid_race = team_race_name(race.name) == (
                "Men" if category == "SM" else "Women"
            )
            if valid_race and (result.club or "").strip().casefold() != "guest":
                positions[category] = positions.get(category, 0) + 1
                updates["category_position"] = positions[category]
            else:
                updates["category_position"] = None
        output.append(result.model_copy(update=updates))
    return output


class ResultsBrowser(BaseModel):
    """The season → fixture → race selection shown on the results page."""

    model_config = ConfigDict(frozen=True)

    seasons: list[Season]
    selected_season: Season | None
    fixtures: list[Fixture]
    round1_results_status: Literal["not_available", "published"] | None
    active_fixture: Fixture | None
    races: list[Race]
    active_race: Race | None
    race_results: list[Result]
    team_round_results: list[TeamRoundResult]
    view_mode: ResultsViewMode


class RacePanel(BaseModel):
    """The races of one fixture with one race selected."""

    model_config = ConfigDict(frozen=True)

    active_fixture: Fixture
    races: list[Race]
    active_race: Race | None
    race_results: list[Result]
    team_round_results: list[TeamRoundResult]
    view_mode: ResultsViewMode


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
        view_mode: ResultsViewMode = "individual",
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
        round1_fixture = fixtures[0] if fixtures else None
        round1_results_status: Literal["not_available", "published"] | None
        if round1_fixture is None:
            round1_results_status = "not_available" if selected_season else None
        elif repository.fixture_has_results(db, round1_fixture.id):
            round1_results_status = "published"
        else:
            round1_results_status = "not_available"
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
            round1_results_status=round1_results_status,
            active_fixture=active_fixture,
            races=races,
            active_race=active_race,
            race_results=(
                _present_race_results(
                    active_race, repository.list_results_for_race(db, active_race.id)
                )
                if active_race
                else []
            ),
            team_round_results=(
                with_divisions(
                    db,
                    active_fixture.season_id,
                    repository.list_team_round_results_for_fixture(
                        db, active_fixture.id
                    ),
                )
                if active_fixture
                else []
            ),
            view_mode=view_mode,
        )

    def race_panel(
        self,
        fixture_id: int,
        race_id: int | None = None,
        view_mode: ResultsViewMode = "individual",
    ) -> RacePanel:
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
                _present_race_results(
                    active_race, repository.list_results_for_race(db, active_race.id)
                )
                if active_race
                else []
            ),
            team_round_results=with_divisions(
                db,
                fixture.season_id,
                repository.list_team_round_results_for_fixture(db, fixture_id),
            ),
            view_mode=view_mode,
        )

    def race_results(self, race_id: int) -> tuple[Race, list[Result]]:
        """Return a race and its results.

        Raises:
            NotFoundError: If the race does not exist.
        """
        race = found(repository.get_race_by_id(self._db, race_id), "Race not found")
        return race, _present_race_results(
            race, repository.list_results_for_race(self._db, race_id)
        )

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

        The path is the logical one: the file may be stored gzipped beside it
        (see :mod:`website.services.archive`).

        Raises:
            NotFoundError: If there is no PDF, or its path escapes *root*.
        """
        not_available = "Source PDF not available"
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if fixture is None or not fixture.source_pdf:
            raise NotFoundError(not_available)
        # Defend against path traversal: resolve inside the known root and verify.
        safe_path = (root / fixture.source_pdf).resolve()
        if (
            not safe_path.is_relative_to(root.resolve())
            or stored_file(safe_path) is None
        ):
            raise NotFoundError(not_available)
        return safe_path
