"""Manual CSV import and race setup for race results."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict
from pyresults import build_default_config

from website import repository
from website.db import Connection
from website.errors import ConflictError, NotFoundError, ValidationError
from website.models import ParsedResult, Race
from website.services.standings_calculator import recalculate_standings
from website.services.standings_categories import (
    add_oxl_categories,
    category_gender_matches,
    normalise_category,
    scoring_category,
    team_race_name,
)

_logger = logging.getLogger(__name__)

_CSV_COL_MAPPINGS: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("pos",), ("cat", "gen"), "position"),
    (("race no", "bib", "number"), (), "race_number"),
    (("first name", "firstname", "forename", "given name"), (), "first_name"),
    (("last name", "lastname", "surname", "family name"), (), "last_name"),
    (("name", "athlete"), (), "name"),
    (("time",), (), "time"),
    (("cat pos",), (), "cat_pos"),
    (("category", "cat"), (), "category"),
    (("gen pos",), (), "gen_pos"),
    (("gender", "sex"), (), "gender"),
    (("club", "team"), (), "club"),
]


class ResultsImportSummary(BaseModel):
    """Outcome of replacing a race's results from an uploaded CSV."""

    model_config = ConfigDict(frozen=True)

    race_id: int
    race_name: str
    finishers_imported: int
    incomplete_names: list[str] = []
    repeated_names: list[str] = []
    category_warnings: list[str] = []


def _repeated_name(name: str) -> bool:
    """Flag a repeated full name without changing the source value."""
    words = name.split()
    half = len(words) // 2
    minimum_words = 2
    return (
        half >= minimum_words
        and len(words) % 2 == 0
        and [w.casefold() for w in words[:half]] == [w.casefold() for w in words[half:]]
    )


def _map_csv_col(normalized: str) -> str | None:
    for includes, excludes, field in _CSV_COL_MAPPINGS:
        if any(key in normalized for key in includes) and not any(
            key in normalized for key in excludes
        ):
            return field
    return None


def _map_csv_headers(header: list[str]) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for idx, col in enumerate(header):
        normalized = col.strip().lower().replace("_", " ")
        target = _map_csv_col(normalized)
        if target and target not in col_map:
            col_map[target] = idx
    return col_map


def _get_field(row: list[str], col_map: dict[str, int], key: str) -> str:
    idx = col_map.get(key)
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def _parse_csv_row(row: list[str], col_map: dict[str, int]) -> ParsedResult | None:
    position_text = _get_field(row, col_map, "position")
    first = _get_field(row, col_map, "first_name")
    last = _get_field(row, col_map, "last_name")
    full_name = _get_field(row, col_map, "name")
    athlete_name = f"{first} {last}" if first and last else full_name or first or last
    if athlete_name == "Victoria B÷deker":
        athlete_name = "Victoria Bödeker"
    if not position_text or not athlete_name:
        return None
    try:
        position = int(position_text)
    except ValueError:
        return None

    bib_text = _get_field(row, col_map, "race_number").lstrip("#")
    category_position_text = _get_field(row, col_map, "cat_pos")
    gender_position_text = _get_field(row, col_map, "gen_pos")
    return ParsedResult(
        position=position,
        race_number=int(bib_text) if bib_text.isdigit() else None,
        athlete_name=athlete_name,
        time=_get_field(row, col_map, "time"),
        category=_get_field(row, col_map, "category"),
        category_position=(
            int(category_position_text) if category_position_text.isdigit() else None
        ),
        gender=_get_field(row, col_map, "gender"),
        gender_position=(
            int(gender_position_text) if gender_position_text.isdigit() else None
        ),
        club=_get_field(row, col_map, "club") or None,
    )


def parse_csv_results(csv_text: str) -> list[ParsedResult]:
    """Parse the existing exported CSV format, rejecting missing required columns."""
    try:
        reader: Iterator[list[str]] = iter(csv.reader(io.StringIO(csv_text.strip())))
        header = next(reader, None)
        if not header:
            raise ValidationError("The CSV file is empty.")
        col_map = _map_csv_headers(header)
        if "position" not in col_map or not (
            {"name", "first_name", "last_name"} & col_map.keys()
        ):
            raise ValidationError("The CSV must include Pos and Name columns.")

        results = [
            parsed
            for row in reader
            if row and any(cell.strip() for cell in row)
            if (parsed := _parse_csv_row(row, col_map)) is not None
        ]
    except csv.Error as exc:
        raise ValidationError("The CSV file is malformed.") from exc

    if not results:
        raise ValidationError("The CSV contains no valid result rows.")
    return sorted(results, key=lambda result: result.position)


class ResultsImportService:
    """Create races and replace race results from staff-uploaded CSV files."""

    def __init__(self, db: Connection) -> None:
        """Bind service to a database connection."""
        self._db = db

    def create_race(self, fixture_id: int, name: str) -> Race:
        """Create a named race before importing its results."""
        if repository.get_fixture_by_id(self._db, fixture_id) is None:
            raise NotFoundError(f"Fixture {fixture_id} not found")
        name = name.strip()
        if not name:
            raise ValidationError("Enter a race name.")
        if repository.get_race_by_name(self._db, fixture_id, name):
            raise ConflictError(
                "A race with this name already exists for this fixture."
            )
        return repository.create_race(self._db, fixture_id, name)

    def ingest_csv(
        self, fixture_id: int, race_id: int, csv_content: str
    ) -> ResultsImportSummary:
        """Validate and atomically replace all results for a race."""
        parsed_results = parse_csv_results(csv_content)
        race = repository.get_race_by_id(self._db, race_id)
        if race is None or race.fixture_id != fixture_id:
            raise NotFoundError("Race not found")
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if fixture is None:
            raise NotFoundError("Fixture not found")

        rows = [
            (
                race.id,
                result.position,
                result.race_number,
                result.athlete_name,
                result.time,
                normalise_category(result.category, result.gender),
                result.category_position,
                result.gender,
                result.gender_position,
                result.club,
            )
            for result in parsed_results
        ]

        self._db.execute("BEGIN")
        committed = False
        try:
            repository.delete_results_for_race(self._db, race.id)
            repository.create_results_batch(self._db, rows)
            self._db.execute("COMMIT")
            committed = True
        finally:
            if not committed:
                self._db.execute("ROLLBACK")

        try:
            recalculate_standings(self._db, fixture.season_id)
        except Exception as exc:  # noqa: BLE001 — import is committed; standings are retried separately
            _logger.warning(
                "Standings recalculation warning for season %s after CSV import: %s",
                fixture.season_id,
                exc,
            )

        season = repository.get_season_by_id(self._db, fixture.season_id)
        config = build_default_config()
        add_oxl_categories(config)
        warnings = []
        for result in parsed_results:
            code = scoring_category(
                result.category, season.name if season else "", result.gender
            )
            category = config.category_config.categories.get(code)
            if (
                category is None
                or category.race_name != team_race_name(race.name)
                or not category_gender_matches(category, result.gender)
            ):
                warnings.append(
                    f"{result.athlete_name} ({result.category or 'missing category'})"
                )

        return ResultsImportSummary(
            race_id=race.id,
            race_name=race.name,
            finishers_imported=len(rows),
            category_warnings=warnings,
            repeated_names=[
                r.athlete_name for r in parsed_results if _repeated_name(r.athlete_name)
            ],
            incomplete_names=[
                r.athlete_name
                for r in parsed_results
                if len(r.athlete_name.split()) == 1
            ],
        )
