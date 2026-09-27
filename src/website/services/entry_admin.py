"""League administration of team entries: overview, pricing and payments."""

import logging

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import ValidationError
from website.models import EntryBatchSummary, Season, SeasonEntryConfig
from website.models.forms import EntryConfigForm
from website.services._common import found

_logger = logging.getLogger(__name__)
_PENCE_PER_POUND = 100


class EntriesOverview(BaseModel):
    """Entry batches across seasons, optionally filtered."""

    model_config = ConfigDict(frozen=True)

    seasons: list[Season]
    batches: list[EntryBatchSummary]


class SeasonEntriesAdmin(BaseModel):
    """One season's entry configuration and batches."""

    model_config = ConfigDict(frozen=True)

    season: Season
    config: SeasonEntryConfig | None
    batches: list[EntryBatchSummary]


class WebhookEvent(BaseModel):
    """The parts of a Stripe Checkout webhook event the site acts on."""

    model_config = ConfigDict(frozen=True)

    type: str
    session_id: str
    payment_intent: str | None = None
    payment_status: str | None = None
    payment_method_types: list[str] = []


class EntryAdminService:
    """Admin views of entries and payment status updates."""

    def __init__(self, db: Connection) -> None:
        """Bind the service to a database connection."""
        self._db = db

    def overview(self, season_id: int | None, status: str | None) -> EntriesOverview:
        """Return batches for one season, or for every season, by status."""
        seasons = repository.list_seasons(self._db)
        season_ids = [season_id] if season_id is not None else [s.id for s in seasons]
        season_names = {s.id: s.name for s in seasons}
        batches = [
            batch.model_copy(
                update={"season_name": season_names.get(batch.season_id, "?")}
            )
            for sid in season_ids
            for batch in repository.list_entry_batches_for_season(
                self._db, sid, status=status
            )
        ]
        return EntriesOverview(seasons=seasons, batches=batches)

    def season(self, season_id: int) -> SeasonEntriesAdmin:
        """Return a season's entry configuration and batches.

        Raises:
            NotFoundError: If the season does not exist.
        """
        season = found(repository.get_season_by_id(self._db, season_id))
        return SeasonEntriesAdmin(
            season=season,
            config=repository.get_season_entry_config(self._db, season_id),
            batches=repository.list_entry_batches_for_season(self._db, season_id),
        )

    def save_config(self, season_id: int, form: EntryConfigForm) -> None:
        """Store a season's entry settings; prices are submitted in pounds.

        Raises:
            NotFoundError: If the season does not exist.
            ValidationError: If a price is negative.
        """
        found(repository.get_season_by_id(self._db, season_id))
        junior = form.junior_pence_per_fixture_display
        adult = form.adult_pence_per_fixture_display
        if junior < 0 or adult < 0:
            raise ValidationError("Prices cannot be negative")
        repository.upsert_season_entry_config(
            self._db,
            season_id=season_id,
            entries_open=form.entries_open,
            ea_reference_date=form.ea_reference_date,
            total_fixtures=form.total_fixtures,
            junior_pence_per_fixture=round(junior * _PENCE_PER_POUND),
            adult_pence_per_fixture=round(adult * _PENCE_PER_POUND),
        )

    def apply_payment_event(self, event: WebhookEvent) -> None:
        """Update a batch's payment status from a Stripe Checkout event."""
        batch = repository.get_entry_batch_by_stripe_session(self._db, event.session_id)
        if batch is None:
            _logger.warning("Stripe webhook: unknown session %s", event.session_id)
            return
        if event.type == "checkout.session.completed":
            if batch.is_paid:
                return
            new_status = (
                "paid" if event.payment_status == "paid" else "payment_initiated"
            )
            method = (
                event.payment_method_types[0] if event.payment_method_types else "card"
            )
            self._set_status(batch.id, new_status, event.payment_intent, method)
        elif event.type == "checkout.session.async_payment_succeeded":
            # BACS debit: the payment arrived after the initial checkout.
            if batch.status != "paid":
                self._set_status(batch.id, "paid", event.payment_intent, None)
        elif event.type == "checkout.session.async_payment_failed":
            self._set_status(batch.id, "payment_failed", None, None)

    def _set_status(
        self,
        batch_id: int,
        status: str,
        payment_intent: str | None,
        payment_method: str | None,
    ) -> None:
        repository.update_batch_status(
            self._db,
            batch_id,
            status,
            stripe_payment_intent_id=payment_intent,
            stripe_payment_method=payment_method,
        )
        if status == "paid":
            repository.assign_race_numbers(self._db, batch_id)
