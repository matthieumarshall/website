"""Season entry configuration and entry batch persistence."""

import datetime as dt

from website.db import Connection
from website.models import EntryBatch, EntryBatchSummary, SeasonEntryConfig
from website.repository._rows import Params, fetch_all, fetch_one, fetch_value, require

_BATCH_SELECT = """
    SELECT id, season_id, club_id, manager_user_id, status,
           fixtures_remaining_at_entry, total_pence,
           stripe_checkout_session_id, stripe_payment_intent_id,
           stripe_payment_method, paid_at, created_at
    FROM entry_batches
"""


def get_season_entry_config(db: Connection, season_id: int) -> SeasonEntryConfig | None:
    """Return a season's entry configuration, or None if not configured."""
    return fetch_one(
        db,
        SeasonEntryConfig,
        "SELECT season_id, entries_open, ea_reference_date, total_fixtures,"
        " junior_pence_per_fixture, adult_pence_per_fixture"
        " FROM season_entry_config WHERE season_id = ?",
        [season_id],
    )


def upsert_season_entry_config(
    db: Connection,
    season_id: int,
    entries_open: bool,
    ea_reference_date: str | dt.date,
    total_fixtures: int,
    junior_pence_per_fixture: int = 0,
    adult_pence_per_fixture: int = 0,
) -> None:
    """Create or replace a season's entry configuration."""
    values = [
        entries_open,
        ea_reference_date,
        total_fixtures,
        junior_pence_per_fixture,
        adult_pence_per_fixture,
    ]
    exists = fetch_value(
        db, "SELECT season_id FROM season_entry_config WHERE season_id = ?", [season_id]
    )
    if exists is not None:
        db.execute(
            """
            UPDATE season_entry_config
            SET entries_open = ?, ea_reference_date = ?, total_fixtures = ?,
                junior_pence_per_fixture = ?, adult_pence_per_fixture = ?
            WHERE season_id = ?
            """,
            [*values, season_id],
        )
    else:
        db.execute(
            "INSERT INTO season_entry_config (entries_open, ea_reference_date,"
            " total_fixtures, junior_pence_per_fixture, adult_pence_per_fixture,"
            " season_id) VALUES (?, ?, ?, ?, ?, ?)",
            [*values, season_id],
        )


def create_entry_batch(
    db: Connection,
    season_id: int,
    club_id: int,
    manager_user_id: int,
    fixtures_remaining_at_entry: int,
    total_pence: int,
) -> EntryBatch:
    """Insert a ``pending_payment`` batch and return it."""
    db.execute(
        """
        INSERT INTO entry_batches
            (season_id, club_id, manager_user_id,
             fixtures_remaining_at_entry, total_pence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [season_id, club_id, manager_user_id, fixtures_remaining_at_entry, total_pence],
    )
    batch = fetch_one(
        db,
        EntryBatch,
        f"{_BATCH_SELECT} WHERE season_id = ? AND club_id = ? AND manager_user_id = ?"
        " ORDER BY id DESC LIMIT 1",
        [season_id, club_id, manager_user_id],
    )
    return require(batch, "entry batch")


def get_entry_batch(db: Connection, batch_id: int) -> EntryBatch | None:
    """Return the batch with *batch_id*, or None."""
    return fetch_one(db, EntryBatch, f"{_BATCH_SELECT} WHERE id = ?", [batch_id])


def get_entry_batch_by_stripe_session(
    db: Connection, session_id: str
) -> EntryBatch | None:
    """Return the batch paid for by a Stripe Checkout session, or None."""
    return fetch_one(
        db,
        EntryBatch,
        f"{_BATCH_SELECT} WHERE stripe_checkout_session_id = ?",
        [session_id],
    )


def update_batch_status(
    db: Connection,
    batch_id: int,
    status: str,
    stripe_payment_intent_id: str | None = None,
    stripe_payment_method: str | None = None,
) -> None:
    """Set a batch's status, stamping ``paid_at`` when it becomes paid."""
    paid_at = ", paid_at = current_timestamp" if status == "paid" else ""
    db.execute(
        f"""
        UPDATE entry_batches
        SET status = ?{paid_at},
            stripe_payment_intent_id = COALESCE(?, stripe_payment_intent_id),
            stripe_payment_method = COALESCE(?, stripe_payment_method)
        WHERE id = ?
        """,  # nosec B608 — `paid_at` is one of two constant strings
        [status, stripe_payment_intent_id, stripe_payment_method, batch_id],
    )


def set_batch_stripe_session(db: Connection, batch_id: int, session_id: str) -> None:
    """Record the Stripe Checkout session created for a batch."""
    db.execute(
        "UPDATE entry_batches SET stripe_checkout_session_id = ? WHERE id = ?",
        [session_id, batch_id],
    )


def list_entry_batches_for_season(
    db: Connection,
    season_id: int,
    club_id: int | None = None,
    status: str | None = None,
) -> list[EntryBatchSummary]:
    """Return batches with club name and manager username joined."""
    where_parts = ["eb.season_id = ?"]
    params: list[object] = [season_id]
    if club_id is not None:
        where_parts.append("eb.club_id = ?")
        params.append(club_id)
    if status is not None:
        where_parts.append("eb.status = ?")
        params.append(status)
    where = " AND ".join(where_parts)
    query_params: Params = params
    return fetch_all(
        db,
        EntryBatchSummary,
        f"""
        SELECT eb.id, eb.club_id, c.name AS club_name, u.username AS manager_username,
               eb.status, eb.fixtures_remaining_at_entry, eb.total_pence,
               eb.stripe_payment_method, eb.paid_at, eb.created_at, eb.season_id
        FROM entry_batches eb
        JOIN clubs c ON c.id = eb.club_id
        JOIN users u ON u.id = eb.manager_user_id
        WHERE {where}
        ORDER BY eb.created_at DESC
        """,  # nosec B608 — `where` is built from constant clauses; values are bound params
        query_params,
    )
