"""Authentication and club manager accounts."""

import logging

from website import repository
from website.db import Connection
from website.errors import ConflictError, ForbiddenError, ValidationError
from website.models import ClubManager, ClubManagerListing, CurrentUser, User, UserRole
from website.models.forms import ClubManagerForm
from website.passwords import hash_password, verify_password

_logger = logging.getLogger(__name__)
MIN_PASSWORD_LENGTH = 12


class AccountService:
    """Verify logins and administer club manager accounts."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user if the credentials are valid, else None."""
        user = repository.get_user_by_username(self._db, username)
        if user is None or not verify_password(password, user.hashed_password):
            _logger.warning("Failed login attempt for username: %s", username)
            return None
        return user

    def active_club_manager(self, user: CurrentUser | None) -> ClubManager:
        """Return the club a signed-in, active club manager looks after.

        Raises:
            ForbiddenError: If the user is not an active club manager.
        """
        if user is None or user.role != UserRole.club_manager.value:
            raise ForbiddenError("Club manager access required")
        manager = repository.get_club_for_manager(self._db, user.id)
        if manager is None or not manager.is_active:
            raise ForbiddenError(
                "Your club manager account is inactive. Please contact the league."
            )
        return manager

    def list_club_managers(self) -> list[ClubManagerListing]:
        """Return every club manager account."""
        return repository.list_club_managers(self._db)

    def create_club_manager(self, form: ClubManagerForm) -> None:
        """Create a club manager login linked to a club.

        Raises:
            ValidationError: If a field is missing, the password is too short
                or the club does not exist.
            ConflictError: If the username is taken.
        """
        username = form.username.strip()
        if not username or not form.password or not form.club_id:
            raise ValidationError("Username, password, and club are required.")
        if len(form.password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        if repository.get_club_by_id(self._db, form.club_id) is None:
            raise ValidationError("Invalid club selected")
        try:
            user = repository.create_user(
                self._db,
                username=username,
                hashed_password=hash_password(form.password),
                role=UserRole.club_manager,
            )
            repository.create_club_manager(
                self._db,
                user_id=user.id,
                club_id=form.club_id,
                email=form.email.strip() or None,
            )
        except repository.IntegrityError as exc:
            raise ConflictError(
                f"Could not create manager. Username '{username}' may already be taken."
            ) from exc

    def toggle_club_manager(self, manager_id: int) -> None:
        """Flip a club manager's active flag."""
        repository.toggle_club_manager_active(self._db, manager_id=manager_id)
