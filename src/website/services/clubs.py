"""Member club management, shared by the in-page editor and admin pages."""

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import ConflictError, ValidationError
from website.models import Club
from website.models.forms import ClubForm
from website.richtext import validate_http_url
from website.services._common import blank_to_none, found

REQUIRED_FIELDS_MESSAGE = "Name, OXL code and EA club ID are required."
DUPLICATE_CODE_MESSAGE = "A club with that OXL code already exists."


class ClubDetails(BaseModel):
    """Normalised, validated club fields."""

    model_config = ConfigDict(frozen=True)

    name: str
    oxl_code: str
    ea_club_id: str
    opentrack_code: str | None
    website_url: str | None
    is_oxfordshire_member: bool
    is_active: bool


def normalise_club(form: ClubForm) -> ClubDetails:
    """Trim and validate a submitted club.

    Raises:
        ValidationError: If a required field is blank or the URL is invalid.
    """
    name = form.name.strip()
    oxl_code = form.oxl_code.strip().upper()
    ea_club_id = form.ea_club_id.strip()
    if not name or not oxl_code or not ea_club_id:
        raise ValidationError(REQUIRED_FIELDS_MESSAGE)
    website_url = form.website_url.strip()
    try:
        normalised_url = validate_http_url(website_url) if website_url else None
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return ClubDetails(
        name=name,
        oxl_code=oxl_code,
        ea_club_id=ea_club_id,
        opentrack_code=blank_to_none(form.opentrack_code),
        website_url=normalised_url,
        is_oxfordshire_member=form.is_oxfordshire_member,
        is_active=form.is_active,
    )


class ClubService:
    """Create, edit and list member clubs."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def list_clubs(self, include_inactive: bool) -> list[Club]:
        """Return all clubs for staff, or only active clubs for the public."""
        if include_inactive:
            return repository.list_clubs(self._db)
        return repository.list_public_clubs(self._db)

    def get(self, club_id: int) -> Club:
        """Return a club.

        Raises:
            NotFoundError: If the club does not exist.
        """
        return found(repository.get_club_by_id(self._db, club_id))

    def create(self, form: ClubForm) -> Club:
        """Create a club.

        Raises:
            ValidationError: If the submission is invalid.
            ConflictError: If the OXL code is already used.
        """
        details = normalise_club(form)
        try:
            return repository.create_club(
                self._db,
                name=details.name,
                oxl_code=details.oxl_code,
                ea_club_id=details.ea_club_id,
                opentrack_code=details.opentrack_code,
                website_url=details.website_url,
                is_oxfordshire_member=details.is_oxfordshire_member,
            )
        except repository.IntegrityError as exc:
            raise ConflictError(DUPLICATE_CODE_MESSAGE) from exc

    def update(self, club_id: int, form: ClubForm) -> Club:
        """Update a club and return it.

        Raises:
            NotFoundError: If the club does not exist.
            ValidationError: If the submission is invalid or conflicts.
        """
        self.get(club_id)
        details = normalise_club(form)
        try:
            repository.update_club(
                self._db,
                club_id=club_id,
                name=details.name,
                oxl_code=details.oxl_code,
                ea_club_id=details.ea_club_id,
                is_active=details.is_active,
                opentrack_code=details.opentrack_code,
                website_url=details.website_url,
                is_oxfordshire_member=details.is_oxfordshire_member,
            )
        except repository.IntegrityError as exc:
            raise ValidationError(str(exc)) from exc
        return self.get(club_id)

    def toggle_active(self, club_id: int) -> Club:
        """Flip a club's active flag and return it.

        Raises:
            NotFoundError: If the club does not exist.
        """
        self.get(club_id)
        repository.toggle_club_active(self._db, club_id)
        return self.get(club_id)
