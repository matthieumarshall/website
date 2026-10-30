"""User accounts and the authenticated session identity."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class UserRole(StrEnum):
    """Roles that grant access to different parts of the site."""

    admin = "admin"
    content_creator = "content_creator"
    club_manager = "club_manager"


STAFF_ROLES = frozenset({UserRole.admin.value, UserRole.content_creator.value})


class User(BaseModel):
    """A stored user account."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    hashed_password: str
    role: UserRole


class CurrentUser(BaseModel):
    """The user identity carried in the session cookie."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    role: str

    @property
    def is_staff(self) -> bool:
        """Return True for admins and content creators."""
        return self.role in STAFF_ROLES
