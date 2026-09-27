"""Small helpers shared by service classes."""

from typing import TypeVar

from website.errors import NotFoundError

T = TypeVar("T")


def found(value: T | None, message: str = "") -> T:
    """Return *value*, or raise :class:`NotFoundError` if it is None.

    Raises:
        NotFoundError: If *value* is None.
    """
    if value is None:
        raise NotFoundError(message)
    return value


def blank_to_none(value: str) -> str | None:
    """Strip *value* and return None if nothing is left."""
    return value.strip() or None
