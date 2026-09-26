"""Division assignment persistence."""

from website.db import Connection
from website.models import DivisionAssignment
from website.repository._rows import fetch_all, fetch_one, fetch_value, require

GENDERS = ("women", "men")
DIVISIONS = (1, 2, 3)

_ASSIGNMENT_SELECT = (
    "SELECT da.id, da.season_id, s.name AS season_name, da.club_id,"
    " c.name AS club_name, da.gender, da.division FROM division_assignments da"
    " JOIN seasons s ON s.id = da.season_id"
    " JOIN clubs c ON c.id = da.club_id"
)
_ASSIGNMENT_ORDER = " ORDER BY s.name DESC, da.gender, da.division, c.name"


def _check_assignment(gender: str, division: int) -> None:
    if gender not in GENDERS or division not in DIVISIONS:
        raise ValueError("Invalid division assignment")


def list_division_assignments(
    db: Connection, season_id: int | None = None
) -> list[DivisionAssignment]:
    """Return assignments, optionally for a single season."""
    if season_id is not None:
        return fetch_all(
            db,
            DivisionAssignment,
            f"{_ASSIGNMENT_SELECT} WHERE da.season_id = ?{_ASSIGNMENT_ORDER}",  # noqa: S608
            [season_id],
        )
    return fetch_all(
        db,
        DivisionAssignment,
        f"{_ASSIGNMENT_SELECT}{_ASSIGNMENT_ORDER}",  # noqa: S608
    )


def get_division_assignment(
    db: Connection, assignment_id: int
) -> DivisionAssignment | None:
    """Return the assignment with *assignment_id*, or None."""
    return fetch_one(
        db,
        DivisionAssignment,
        f"{_ASSIGNMENT_SELECT} WHERE da.id = ?",  # noqa: S608
        [assignment_id],
    )


def create_division_assignment(
    db: Connection, season_id: int, club_id: int, gender: str, division: int
) -> DivisionAssignment:
    """Assign a club to a division and return the assignment.

    Raises:
        ValueError: If *gender* or *division* is invalid.
        duckdb.ConstraintException: If the club is already assigned.
    """
    _check_assignment(gender, division)
    db.execute(
        "INSERT INTO division_assignments"
        " (season_id, club_id, gender, division) VALUES (?, ?, ?, ?)",
        [season_id, club_id, gender, division],
    )
    assignment_id = fetch_value(
        db,
        "SELECT id FROM division_assignments WHERE season_id = ?"
        " AND club_id = ? AND gender = ?",
        [season_id, club_id, gender],
    )
    assignment = (
        get_division_assignment(db, assignment_id)
        if isinstance(assignment_id, int)
        else None
    )
    return require(assignment, "division assignment")


def update_division_assignment(  # noqa: PLR0913 — one parameter per column
    db: Connection,
    assignment_id: int,
    season_id: int,
    club_id: int,
    gender: str,
    division: int,
) -> None:
    """Update every field of an assignment.

    Raises:
        ValueError: If *gender* or *division* is invalid.
    """
    _check_assignment(gender, division)
    db.execute(
        "UPDATE division_assignments SET season_id = ?, club_id = ?, gender = ?,"
        " division = ?, updated_at = current_timestamp WHERE id = ?",
        [season_id, club_id, gender, division, assignment_id],
    )


def delete_division_assignment(db: Connection, assignment_id: int) -> None:
    """Delete an assignment."""
    db.execute("DELETE FROM division_assignments WHERE id = ?", [assignment_id])
