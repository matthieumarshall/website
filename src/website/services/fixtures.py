"""Seasons, fixtures and fixture images."""

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from website import repository
from website.db import Connection
from website.errors import ConflictError, InvalidRequestError, ValidationError
from website.integrations.geocoding import Geocoder
from website.models import (
    MAX_FIXTURES_PER_SEASON,
    Fixture,
    FixtureCreate,
    FixtureImage,
    Season,
    SeasonCreate,
)
from website.models.fixtures import parse_timetable_json
from website.models.forms import FixtureForm
from website.services._common import found
from website.services.uploads import FileStore, UploadedFile


class FixturesView(BaseModel):
    """A season's fixtures with the first fixture expanded."""

    model_config = ConfigDict(frozen=True)

    seasons: list[Season]
    selected_season: Season | None
    fixtures: list[Fixture]
    active_fixture: Fixture | None
    images: list[FixtureImage]


class FixtureDetail(BaseModel):
    """Everything shown in a fixture's detail panel."""

    model_config = ConfigDict(frozen=True)

    fixture: Fixture
    season: Season | None
    images: list[FixtureImage]
    has_results: bool


class FixtureImages(BaseModel):
    """A fixture's image gallery after an upload or delete."""

    model_config = ConfigDict(frozen=True)

    fixture: Fixture | None
    season: Season | None
    images: list[FixtureImage]


def _validated_fixture(form: FixtureForm) -> FixtureCreate:
    try:
        return FixtureCreate.model_validate(
            {
                "title": form.title.strip(),
                "date": form.date,
                "location_name": form.location_name.strip(),
                "address": form.address.strip(),
                "timetable": parse_timetable_json(form.timetable_json),
                "travel_instructions": form.travel_instructions.strip(),
                "what3words_word1": form.what3words_word1,
                "what3words_word2": form.what3words_word2,
                "what3words_word3": form.what3words_word3,
            }
        )
    except PydanticValidationError as exc:
        message = "; ".join(str(error["msg"]) for error in exc.errors())
        raise ValidationError(message) from exc


def _what3words(fixture: FixtureCreate) -> str | None:
    """Join the three words, which must be given together or not at all."""
    words = fixture.what3words_words
    if any(words) and not all(words):
        raise InvalidRequestError(
            "All three What3Words words must be provided together"
        )
    return ".".join(words) if all(words) else None


class FixtureService:
    """Fixture calendar management for the public site and staff editors."""

    def __init__(
        self, db: Connection, geocoder: Geocoder, image_store: FileStore
    ) -> None:
        """Bind the service to a database, a geocoder and the fixture image store."""
        self._db = db
        self._geocoder = geocoder
        self._images = image_store

    def season_view(self, season_id: int | None) -> FixturesView:
        """Return a season's fixtures (default: latest season)."""
        db = self._db
        seasons = repository.list_seasons(db)
        if season_id is None and seasons:
            season_id = seasons[0].id
        selected = (
            repository.get_season_by_id(db, season_id)
            if season_id is not None
            else None
        )
        fixtures = (
            repository.list_fixtures_for_season(db, selected.id) if selected else []
        )
        first = fixtures[0] if fixtures else None
        return FixturesView(
            seasons=seasons,
            selected_season=selected,
            fixtures=fixtures,
            active_fixture=first,
            images=repository.list_fixture_images(db, first.id) if first else [],
        )

    def detail(self, fixture_id: int) -> FixtureDetail:
        """Return a fixture's detail panel.

        Raises:
            NotFoundError: If the fixture does not exist.
        """
        db = self._db
        fixture = found(
            repository.get_fixture_by_id(db, fixture_id), "Fixture not found"
        )
        return FixtureDetail(
            fixture=fixture,
            season=repository.get_season_by_id(db, fixture.season_id),
            images=repository.list_fixture_images(db, fixture_id),
            has_results=repository.fixture_has_results(db, fixture_id),
        )

    def get_season(self, season_id: int) -> Season:
        """Return a season.

        Raises:
            NotFoundError: If the season does not exist.
        """
        return found(
            repository.get_season_by_id(self._db, season_id), "Season not found"
        )

    def season_or_none(self, season_id: int) -> Season | None:
        """Return a season, or None if it does not exist."""
        return repository.get_season_by_id(self._db, season_id)

    def get_fixture(self, fixture_id: int) -> Fixture:
        """Return a fixture.

        Raises:
            NotFoundError: If the fixture does not exist.
        """
        return found(
            repository.get_fixture_by_id(self._db, fixture_id), "Fixture not found"
        )

    def list_seasons(self) -> list[Season]:
        """Return every season, latest first."""
        return repository.list_seasons(self._db)

    def create_season(self, name: str) -> Season:
        """Create a season.

        Raises:
            ValidationError: If the name is blank.
            ConflictError: If a season with that name exists.
        """
        validated = SeasonCreate(name=name.strip())
        if not validated.name:
            raise ValidationError("Season name cannot be empty")
        try:
            return repository.create_season(self._db, validated.name)
        except repository.IntegrityError as exc:
            raise ConflictError("A season with that name already exists") from exc

    def delete_season(self, season_id: int) -> None:
        """Delete an empty season.

        Raises:
            ConflictError: If the season still has fixtures.
        """
        try:
            repository.delete_season(self._db, season_id)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def season_for_new_fixture(self, season_id: int) -> Season:
        """Return a season that still has room for another fixture.

        Raises:
            NotFoundError: If the season does not exist.
            ConflictError: If the season is already full.
        """
        season = self.get_season(season_id)
        count = repository.count_fixtures_for_season(self._db, season_id)
        if count >= MAX_FIXTURES_PER_SEASON:
            raise ConflictError(
                f"Season already has {count} fixtures "
                f"(maximum is {MAX_FIXTURES_PER_SEASON})."
            )
        return season

    def _coordinates(self, address: str) -> tuple[float | None, float | None]:
        coords = self._geocoder.geocode(address)
        return (coords[0], coords[1]) if coords else (None, None)

    def create_fixture(self, season_id: int, form: FixtureForm) -> Fixture:
        """Create a fixture, geocoding its address.

        Raises:
            ValidationError: If the submitted details are invalid.
            InvalidRequestError: If only some what3words words are given.
            ConflictError: If the season is already full.
        """
        fixture = _validated_fixture(form)
        what3words = _what3words(fixture)
        latitude, longitude = self._coordinates(fixture.address)
        try:
            return repository.create_fixture(
                self._db,
                season_id=season_id,
                title=fixture.title,
                date=str(fixture.date),
                location_name=fixture.location_name,
                address=fixture.address,
                timetable=fixture.timetable,
                travel_instructions=fixture.travel_instructions,
                latitude=latitude,
                longitude=longitude,
                what3words=what3words,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def update_fixture(self, fixture_id: int, form: FixtureForm) -> Fixture:
        """Update a fixture, re-geocoding its address.

        Raises:
            ValidationError: If the submitted details are invalid.
            InvalidRequestError: If only some what3words words are given.
            NotFoundError: If the fixture does not exist.
        """
        fixture = _validated_fixture(form)
        what3words = _what3words(fixture)
        latitude, longitude = self._coordinates(fixture.address)
        updated = repository.update_fixture(
            self._db,
            fixture_id=fixture_id,
            title=fixture.title,
            date=str(fixture.date),
            location_name=fixture.location_name,
            address=fixture.address,
            timetable=fixture.timetable,
            travel_instructions=fixture.travel_instructions,
            latitude=latitude,
            longitude=longitude,
            what3words=what3words,
        )
        return found(updated, "Fixture not found")

    def delete_fixture(self, fixture_id: int) -> None:
        """Delete a fixture."""
        repository.delete_fixture(self._db, fixture_id)

    def _gallery(self, fixture: Fixture | None, fixture_id: int) -> FixtureImages:
        return FixtureImages(
            fixture=fixture,
            season=(
                repository.get_season_by_id(self._db, fixture.season_id)
                if fixture
                else None
            ),
            images=repository.list_fixture_images(self._db, fixture_id),
        )

    def add_image(self, fixture_id: int, upload: UploadedFile) -> FixtureImages:
        """Store an uploaded image for a fixture.

        Raises:
            NotFoundError: If the fixture does not exist.
            InvalidRequestError: If the file is not a supported image.
            PayloadTooLargeError: If the image is too large.
        """
        fixture = self.get_fixture(fixture_id)
        filename = self._images.save(upload)
        repository.create_fixture_image(
            self._db, fixture_id=fixture_id, filename=filename
        )
        return self._gallery(fixture, fixture_id)

    def delete_image(self, fixture_id: int, image_id: int) -> FixtureImages:
        """Delete a fixture image record and its file."""
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        filename = repository.delete_fixture_image(self._db, image_id)
        if filename is not None:
            self._images.delete(filename)
        return self._gallery(fixture, fixture_id)
