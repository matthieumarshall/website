"""Resolve imported names to member club identities without guessing."""

from collections import defaultdict

from website import repository
from website.db import Connection
from website.errors import ValidationError
from website.models.clubs import Club
from website.models.competition import ClubAlias
from website.repository import club_aliases


def normalise_name(name: str) -> str:
    """Normalise case and whitespace without changing a club's display name."""
    return " ".join(name.split()).casefold()


def list_aliases(db: Connection) -> list[ClubAlias]:
    """Return all staff-maintained aliases."""
    return club_aliases.list_aliases(db)


class ClubRegistry:
    """A snapshot of club identities, including ambiguous names."""

    def __init__(self, clubs: list[Club], aliases: list[ClubAlias]) -> None:
        self.clubs = {club.id: club for club in clubs}
        names: dict[str, set[int]] = defaultdict(set)
        for club in clubs:
            names[normalise_name(club.name)].add(club.id)
        for alias in aliases:
            if alias.club_id in self.clubs:
                names[normalise_name(alias.name)].add(alias.club_id)
        self._names = names

    @classmethod
    def load(cls, db: Connection) -> "ClubRegistry":
        """Load club names and their managed aliases."""
        return cls(repository.list_clubs(db), list_aliases(db))

    def resolve(self, name: str | None) -> Club | None:
        """Return a club only if the name identifies exactly one club."""
        ids = self._names.get(normalise_name(name or ""), set())
        return self.clubs[next(iter(ids))] if len(ids) == 1 else None

    def contains_name(self, name: str) -> bool:
        """Return whether a name is already used, including ambiguous names."""
        return normalise_name(name) in self._names

    def owners(self, name: str) -> set[int]:
        """Return all clubs that claim a name, including ambiguous matches."""
        return set(self._names.get(normalise_name(name), set()))


class ClubIdentityService:
    """Manage aliases and identify names which need staff attention."""

    def __init__(self, db: Connection) -> None:
        self._db = db

    def aliases(self) -> list[ClubAlias]:
        """Return the current aliases."""
        return list_aliases(self._db)

    def unresolved_names(self) -> list[str]:
        """Find imported names with no unambiguous club identity."""
        registry = ClubRegistry.load(self._db)
        return [
            name
            for name in club_aliases.imported_club_names(self._db)
            if normalise_name(name) not in ("", "guest")
            and registry.resolve(name) is None
        ]

    def add(self, club_id: int, name: str) -> None:
        """Add a unique alias for a known club.

        Raises:
            ValidationError: If the club or name is invalid or already in use.
        """
        registry = ClubRegistry.load(self._db)
        name = " ".join(name.split())
        if club_id not in registry.clubs or not name:
            raise ValidationError("Choose a club and enter a result name.")
        if registry.contains_name(name):
            raise ValidationError("That name is already used by a club or alias.")
        if normalise_name(name) == "guest":
            raise ValidationError("Guest is reserved for non-scoring runners.")
        club_aliases.add_alias(self._db, club_id, name)

    def remove(self, alias_id: int) -> None:
        """Remove an alias without changing the original results."""
        club_aliases.remove_alias(self._db, alias_id)
