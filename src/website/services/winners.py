"""Past winners and administrative winner overrides."""

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import ValidationError
from website.models import PublicWinner, Season, WinnerOverride
from website.models.forms import WinnerOverrideForm
from website.services._common import blank_to_none, found


class WinnerDetails(BaseModel):
    """Normalised, validated winner override fields."""

    model_config = ConfigDict(frozen=True)

    season_id: int
    winner_type: str
    category: str
    winner_name: str
    club: str | None
    total_score: int | None
    note: str | None
    mode: str


WinnersByType = dict[str, list[PublicWinner]]


def _parse_score(raw: str) -> int | None:
    if not raw.strip():
        return None
    try:
        score = int(raw)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if score < 0:
        raise ValidationError("Score cannot be negative.")
    return score


class WinnerService:
    """Publish standings winners and manage corrections to them."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def winners_by_type(self) -> WinnersByType:
        """Return public winners split into individual and team lists."""
        grouped: WinnersByType = {"individual": [], "team": []}
        for winner in repository.list_public_winners(self._db):
            grouped[winner.winner_type].append(winner)
        return grouped

    def list_overrides(self) -> list[WinnerOverride]:
        """Return every override."""
        return repository.list_winner_overrides(self._db)

    def list_seasons(self) -> list[Season]:
        """Return every season (for the season picker)."""
        return repository.list_seasons(self._db)

    def get(self, override_id: int) -> WinnerOverride:
        """Return an override.

        Raises:
            NotFoundError: If the override does not exist.
        """
        return found(repository.get_winner_override(self._db, override_id))

    def _details(self, form: WinnerOverrideForm) -> WinnerDetails:
        if repository.get_season_by_id(self._db, form.season_id) is None:
            raise ValidationError("Select a valid season.")
        category = form.category.strip()
        winner_name = form.winner_name.strip()
        if not category or not winner_name:
            raise ValidationError("Category and winner are required.")
        return WinnerDetails(
            season_id=form.season_id,
            winner_type=form.winner_type,
            category=category,
            winner_name=winner_name,
            club=blank_to_none(form.club),
            total_score=_parse_score(form.total_score),
            note=blank_to_none(form.note),
            mode=form.mode,
        )

    def create(self, form: WinnerOverrideForm, user_id: int | None) -> WinnerOverride:
        """Create an override.

        Raises:
            ValidationError: If the submission is invalid.
        """
        details = self._details(form)
        try:
            return repository.create_winner_override(
                self._db, updated_by_id=user_id, **details.model_dump()
            )
        except (ValueError, repository.IntegrityError) as exc:
            raise ValidationError(str(exc)) from exc

    def update(
        self, override_id: int, form: WinnerOverrideForm, user_id: int | None
    ) -> None:
        """Update an override.

        Raises:
            NotFoundError: If the override does not exist.
            ValidationError: If the submission is invalid.
        """
        self.get(override_id)
        details = self._details(form)
        try:
            repository.update_winner_override(
                self._db,
                override_id=override_id,
                updated_by_id=user_id,
                **details.model_dump(),
            )
        except (ValueError, repository.IntegrityError) as exc:
            raise ValidationError(str(exc)) from exc

    def delete(self, override_id: int) -> None:
        """Delete an override.

        Raises:
            NotFoundError: If the override does not exist.
        """
        self.get(override_id)
        repository.delete_winner_override(self._db, override_id)

    def toggle_active(self, override_id: int, user_id: int | None) -> None:
        """Flip an override's active flag.

        Raises:
            NotFoundError: If the override does not exist.
        """
        self.get(override_id)
        repository.toggle_winner_override(self._db, override_id, user_id)
