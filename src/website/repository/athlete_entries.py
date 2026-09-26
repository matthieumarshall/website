"""Athlete entry, race number and club allocation persistence."""

from website.db import Connection
from website.models import (
    AthleteEntryListing,
    AthleteEntryRow,
    ClubAllocationRow,
    PaidAthleteEntry,
)
from website.repository._rows import fetch_all, fetch_count, fetch_value


def get_entered_ea_urns(db: Connection, season_id: int, club_id: int) -> set[int]:
    """Return EA URNs already entered by this club this season (any status)."""
    rows = db.execute(
        "SELECT ea_urn FROM athlete_entries WHERE season_id = ? AND club_id = ?",
        [season_id, club_id],
    ).fetchall()
    return {int(row[0]) for row in rows}


def create_athlete_entries(
    db: Connection,
    batch_id: int,
    season_id: int,
    club_id: int,
    athletes: list[AthleteEntryRow],
) -> None:
    """Insert one entry row per athlete in a batch."""
    for athlete in athletes:
        db.execute(
            """
            INSERT INTO athlete_entries
                (batch_id, season_id, club_id, ea_urn, athlete_name, date_of_birth,
                 ea_age_category, is_junior, amount_pence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                batch_id,
                season_id,
                club_id,
                athlete.ea_urn,
                athlete.athlete_name,
                athlete.date_of_birth,
                athlete.ea_age_category,
                athlete.is_junior,
                athlete.amount_pence,
            ],
        )


def get_athlete_entries_for_batch(
    db: Connection, batch_id: int
) -> list[AthleteEntryRow]:
    """Return a batch's athletes in entry order."""
    return fetch_all(
        db,
        AthleteEntryRow,
        """
        SELECT ea_urn, athlete_name, date_of_birth, ea_age_category,
               is_junior, amount_pence, race_number
        FROM athlete_entries WHERE batch_id = ? ORDER BY id
        """,
        [batch_id],
    )


def list_athlete_entries_for_season(
    db: Connection, season_id: int
) -> list[AthleteEntryListing]:
    """Return all paid/payment_initiated entries for a season, with club name."""
    return fetch_all(
        db,
        AthleteEntryListing,
        """
        SELECT ae.ea_urn, ae.athlete_name, ae.ea_age_category, ae.race_number,
               c.name AS club_name, c.id AS club_id
        FROM athlete_entries ae
        JOIN entry_batches eb ON eb.id = ae.batch_id
        JOIN clubs c ON c.id = ae.club_id
        WHERE ae.season_id = ? AND eb.status IN ('paid', 'payment_initiated')
        ORDER BY c.name, ae.ea_age_category, ae.athlete_name
        """,
        [season_id],
    )


def assign_race_numbers(db: Connection, batch_id: int) -> None:
    """Assign sequential race numbers to all athletes in a batch that lack one."""
    season_id = fetch_value(
        db, "SELECT season_id FROM entry_batches WHERE id = ?", [batch_id]
    )
    if season_id is None:
        return
    max_number = fetch_value(
        db,
        "SELECT COALESCE(MAX(race_number), 0) FROM athlete_entries WHERE season_id = ?",
        [season_id],
    )
    next_number = (max_number if isinstance(max_number, int) else 0) + 1
    athlete_ids = db.execute(
        "SELECT id FROM athlete_entries WHERE batch_id = ? AND race_number IS NULL"
        " ORDER BY id",
        [batch_id],
    ).fetchall()
    for (athlete_entry_id,) in athlete_ids:
        db.execute(
            "UPDATE athlete_entries SET race_number = ? WHERE id = ?",
            [next_number, athlete_entry_id],
        )
        next_number += 1


def update_athlete_race_number(
    db: Connection, athlete_id: int, race_number: int
) -> None:
    """Update an athlete's race number.

    Raises:
        ValueError: If *race_number* is not positive.
    """
    if race_number <= 0:
        raise ValueError("race_number must be greater than 0")
    db.execute(
        "UPDATE athlete_entries SET race_number = ? WHERE id = ?",
        [race_number, athlete_id],
    )


def upsert_club_allocation(
    db: Connection, season_id: int, club_id: int, allocated_slots: int
) -> None:
    """Insert or update a club's athlete entry allocation for a season.

    Raises:
        ValueError: If *allocated_slots* is not positive.
    """
    if allocated_slots <= 0:
        raise ValueError("allocated_slots must be greater than 0")
    db.execute(
        """
        INSERT INTO club_allocations (season_id, club_id, allocated_slots, created_at, updated_at)
        VALUES (?, ?, ?, now(), now())
        ON CONFLICT(season_id, club_id) DO UPDATE SET
            allocated_slots = excluded.allocated_slots,
            updated_at = now()
        """,
        [season_id, club_id, allocated_slots],
    )


def get_club_allocation(db: Connection, season_id: int, club_id: int) -> int | None:
    """Return allocated slots for a club in a season, or None if not set."""
    value = fetch_value(
        db,
        "SELECT allocated_slots FROM club_allocations WHERE season_id = ? AND club_id = ?",
        [season_id, club_id],
    )
    return value if isinstance(value, int) else None


def get_club_athlete_count(db: Connection, season_id: int, club_id: int) -> int:
    """Count paid athlete entries for a club in a season."""
    return fetch_count(
        db,
        """
        SELECT COUNT(ae.id)
        FROM athlete_entries ae
        JOIN entry_batches eb ON eb.id = ae.batch_id
        WHERE ae.season_id = ? AND ae.club_id = ? AND eb.status = 'paid'
        """,
        [season_id, club_id],
    )


def list_club_allocations_for_season(
    db: Connection, season_id: int
) -> list[ClubAllocationRow]:
    """Return all clubs with their allocations and current usage for a season."""
    return fetch_all(
        db,
        ClubAllocationRow,
        """
        SELECT c.id AS club_id, c.name AS club_name,
               COALESCE(ca.allocated_slots, 0) AS allocated_slots,
               COUNT(CASE WHEN eb.status = 'paid' THEN ae.id END) AS current_used,
               CASE WHEN COALESCE(ca.allocated_slots, 0) > 0
                    THEN GREATEST(0, COALESCE(ca.allocated_slots, 0)
                         - COUNT(CASE WHEN eb.status = 'paid' THEN ae.id END))
                    ELSE 0 END AS remaining
        FROM clubs c
        LEFT JOIN club_allocations ca ON ca.club_id = c.id AND ca.season_id = ?
        LEFT JOIN entry_batches eb ON eb.club_id = c.id AND eb.season_id = ?
        LEFT JOIN athlete_entries ae ON ae.batch_id = eb.id
        WHERE eb.id IS NOT NULL OR ca.season_id IS NOT NULL
        GROUP BY c.id, c.name, ca.allocated_slots
        ORDER BY c.name
        """,
        [season_id, season_id],
    )


def list_paid_athlete_entries_for_season(
    db: Connection, season_id: int
) -> list[PaidAthleteEntry]:
    """Return all paid athlete entries for a season, sorted by club and name."""
    return fetch_all(
        db,
        PaidAthleteEntry,
        """
        SELECT ae.id AS athlete_id, c.name AS club_name, ae.athlete_name,
               ae.ea_age_category AS age_category, ae.date_of_birth, ae.ea_urn,
               ae.race_number
        FROM athlete_entries ae
        JOIN clubs c ON c.id = ae.club_id
        JOIN entry_batches eb ON eb.id = ae.batch_id
        WHERE ae.season_id = ? AND eb.status = 'paid'
        ORDER BY c.name, ae.athlete_name
        """,
        [season_id],
    )
