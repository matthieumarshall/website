"""Pure business rules for team entries: age categories and deadlines."""

from collections.abc import Iterable
from datetime import date, datetime, time, timezone

JUNIOR_CATEGORIES = frozenset({"U9", "U11", "U13", "U15", "U17"})

# (maximum age, category), checked in order; anyone older is a Veteran.
_AGE_BANDS = (
    (8, "U9"),
    (10, "U11"),
    (12, "U13"),
    (14, "U15"),
    (16, "U17"),
    (19, "U20"),
    (34, "Senior"),
)
_ENTRY_DEADLINE = time(12, 0)


def get_oxl_age_category(dob: date, reference_date: date) -> str:
    """Return the OXL age category (U9, U11, …, Veteran) for an athlete.

    Age is calculated as of *reference_date* (typically 31 Aug of the season
    start year, per UK Athletics standard).
    """
    age = (
        reference_date.year
        - dob.year
        - ((reference_date.month, reference_date.day) < (dob.month, dob.day))
    )
    for max_age, category in _AGE_BANDS:
        if age <= max_age:
            return category
    return "Veteran"


def is_junior(category: str) -> bool:
    """Return True if the age category qualifies for junior (lower) pricing."""
    return category in JUNIOR_CATEGORIES


def is_entry_open_for_fixture(fixture_date: date) -> bool:
    """Return True if the fixture's entry deadline (midday UTC) has not passed."""
    deadline = datetime.combine(fixture_date, _ENTRY_DEADLINE, tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < deadline


def count_open_fixtures(fixture_dates: Iterable[date]) -> int:
    """Count the fixtures whose entry deadline has not passed."""
    return sum(
        1 for fixture_date in fixture_dates if is_entry_open_for_fixture(fixture_date)
    )
