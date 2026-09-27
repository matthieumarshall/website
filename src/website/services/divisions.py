"""Senior division assignments."""

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import ValidationError
from website.models import Club, DivisionAssignment, DivisionMember, Season
from website.models.forms import DivisionAssignForm
from website.services._common import found

DivisionTable = dict[str, dict[int, list[DivisionMember]]]


class DivisionsView(BaseModel):
    """One season's division tables, by gender then division number."""

    model_config = ConfigDict(frozen=True)

    season: Season | None
    seasons: list[Season]
    assignments: DivisionTable


class DivisionService:
    """View and edit which clubs are in which division each season."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def view(self, season_id: int | None) -> DivisionsView:
        """Return *season_id*'s divisions (default: latest season)."""
        db = self._db
        seasons = repository.list_seasons(db)
        season = (
            repository.get_season_by_id(db, season_id)
            if season_id is not None
            else None
        )
        if season is None and seasons:
            season = seasons[0]
        if season is None:
            return DivisionsView(season=None, seasons=seasons, assignments={})
        table: DivisionTable = {
            "women": {1: [], 2: [], 3: []},
            "men": {1: [], 2: [], 3: []},
        }
        clubs_by_id = {club.id: club for club in repository.list_clubs(db)}
        for assignment in repository.list_division_assignments(db, season.id):
            club = clubs_by_id.get(assignment.club_id)
            table[assignment.gender][assignment.division].append(
                DivisionMember(
                    assignment_id=assignment.id,
                    club_id=assignment.club_id,
                    name=assignment.club_name,
                    website_url=club.website_url if club else None,
                )
            )
        return DivisionsView(season=season, seasons=seasons, assignments=table)

    def list_assignments(self) -> list[DivisionAssignment]:
        """Return every assignment across all seasons."""
        return repository.list_division_assignments(self._db)

    def list_clubs(self) -> list[Club]:
        """Return every club (for the assignment picker)."""
        return repository.list_clubs(self._db)

    def list_seasons(self) -> list[Season]:
        """Return every season (for the season picker)."""
        return repository.list_seasons(self._db)

    def assign(self, form: DivisionAssignForm) -> None:
        """Place a club in a division.

        Raises:
            ValidationError: If the season, club or placement is invalid.
        """
        db = self._db
        if repository.get_season_by_id(db, form.season_id) is None:
            raise ValidationError("Select a valid season.")
        if repository.get_club_by_id(db, form.club_id) is None:
            raise ValidationError("Select a valid club.")
        try:
            repository.create_division_assignment(
                db, form.season_id, form.club_id, form.gender, form.division
            )
        except (ValueError, repository.IntegrityError) as exc:
            raise ValidationError(str(exc)) from exc

    def remove(self, assignment_id: int) -> None:
        """Delete an assignment.

        Raises:
            NotFoundError: If the assignment does not exist.
        """
        found(repository.get_division_assignment(self._db, assignment_id))
        repository.delete_division_assignment(self._db, assignment_id)

    def move(self, assignment_id: int, division: int) -> None:
        """Move an assignment to another division.

        Raises:
            NotFoundError: If the assignment does not exist.
            ValidationError: If the division is invalid.
        """
        assignment = found(repository.get_division_assignment(self._db, assignment_id))
        try:
            repository.update_division_assignment(
                self._db,
                assignment_id=assignment.id,
                season_id=assignment.season_id,
                club_id=assignment.club_id,
                gender=assignment.gender,
                division=division,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
