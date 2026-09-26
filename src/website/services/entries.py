"""Team entries made by club managers: selection, batches, checkout, receipts."""

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict

from website import repository
from website.db import Connection
from website.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    OperationFailedError,
    ServiceUnavailableError,
    ValidationError,
)
from website.integrations.england_athletics import AthleteDirectory
from website.integrations.stripe_payments import CheckoutRequest, PaymentGateway
from website.models import (
    PAYABLE_STATUSES,
    AthleteChoice,
    AthleteEntryListing,
    AthleteEntryRow,
    ClubManager,
    EAAthlete,
    EntryBatch,
    Season,
    SeasonEntryConfig,
)
from website.services._common import found
from website.services.entry_rules import (
    count_open_fixtures,
    get_oxl_age_category,
    is_junior,
)

_PAYMENT_METHOD_LABELS = {"card": "Card", "bacs_debit": "BACS Direct Debit"}


class AthleteSelection(BaseModel):
    """The athlete picker for a club's entries, with per-athlete prices."""

    model_config = ConfigDict(frozen=True)

    season: Season
    athletes: list[AthleteChoice]
    junior_pence_per_fixture: int
    adult_pence_per_fixture: int
    junior_total_pence: int
    adult_total_pence: int
    fixtures_remaining: int


class BatchPreview(BaseModel):
    """An unpaid batch summarised before checkout."""

    model_config = ConfigDict(frozen=True)

    season: Season
    batch: EntryBatch
    athletes: list[AthleteEntryRow]
    junior_count: int
    adult_count: int
    junior_total: int
    adult_total: int


class CheckoutOutcome(BaseModel):
    """Where to send the manager after asking to pay for a batch."""

    model_config = ConfigDict(frozen=True)

    url: str
    started: bool  # False when the batch no longer needs paying


class SeasonEntries(BaseModel):
    """All paid entries for a season, grouped by club."""

    model_config = ConfigDict(frozen=True)

    season: Season
    entries_by_club: dict[str, list[AthleteEntryListing]]
    can_add_more: bool


class Receipt(BaseModel):
    """The contents of a payment receipt."""

    model_config = ConfigDict(frozen=True)

    batch_id: int
    athletes: list[AthleteEntryRow]
    club_name: str
    manager_username: str
    season_name: str
    total_pence: int
    paid_at_display: str
    payment_method_display: str
    generated_at: str


class _Pricing(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: SeasonEntryConfig
    fixtures_remaining: int
    junior_per_fixture: int
    adult_per_fixture: int

    def amount_for(self, junior: bool) -> int:
        per_fixture = self.junior_per_fixture if junior else self.adult_per_fixture
        return per_fixture * self.fixtures_remaining


def _receipt_from(
    batch: EntryBatch,
    athletes: list[AthleteEntryRow],
    club_name: str | None,
    manager_username: str | None,
    season_name: str | None,
) -> Receipt:
    return Receipt(
        batch_id=batch.id,
        athletes=athletes,
        club_name=club_name or "—",
        manager_username=manager_username or "—",
        season_name=season_name or "—",
        total_pence=batch.total_pence,
        paid_at_display=(
            batch.paid_at.strftime("%d %b %Y %H:%M") if batch.paid_at else "—"
        ),
        payment_method_display=_PAYMENT_METHOD_LABELS.get(
            batch.stripe_payment_method or "", "—"
        ),
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    )


class EntryService:
    """Everything a club manager does to enter athletes for a season."""

    def __init__(
        self, db: Connection, athletes: AthleteDirectory, payments: PaymentGateway
    ) -> None:
        """Bind the service to a database, an athlete directory and a payment gateway."""
        self._db = db
        self._athletes = athletes
        self._payments = payments

    # -- rules ---------------------------------------------------------------

    def fixtures_remaining(self, season_id: int) -> int:
        """Count the season's fixtures whose entry deadline has not passed."""
        return count_open_fixtures(repository.list_fixture_dates(self._db, season_id))

    def check_allocation(self, season_id: int, club_id: int, count_to_add: int) -> bool:
        """Return True if the club has room for *count_to_add* more athletes."""
        allocation = repository.get_club_allocation(self._db, season_id, club_id)
        if allocation is None:
            return False  # no allocation set: no entries allowed
        current = repository.get_club_athlete_count(self._db, season_id, club_id)
        return current + count_to_add <= allocation

    def _season(self, season_id: int) -> Season:
        return found(repository.get_season_by_id(self._db, season_id))

    def _open_config(self, season_id: int) -> SeasonEntryConfig:
        config = repository.get_season_entry_config(self._db, season_id)
        if config is None or not config.entries_open:
            raise ForbiddenError("Entries are not open for this season.")
        return config

    def _pricing(self, config: SeasonEntryConfig) -> _Pricing:
        return _Pricing(
            config=config,
            fixtures_remaining=self.fixtures_remaining(config.season_id),
            junior_per_fixture=config.junior_pence_per_fixture or 0,
            adult_per_fixture=config.adult_pence_per_fixture or 0,
        )

    def _club_athletes(self, club_id: int) -> list[EAAthlete]:
        club = repository.get_club_by_id(self._db, club_id)
        if club is None:
            raise OperationFailedError("Club configuration error.")
        return self._athletes.fetch_club_athletes(club.ea_club_id)

    # -- selection and batches -----------------------------------------------

    def athlete_selection(
        self, season_id: int, manager: ClubManager
    ) -> AthleteSelection:
        """List the club's EA athletes with category, price and entry status.

        Raises:
            NotFoundError: If the season does not exist.
            ForbiddenError: If entries are closed or no fixtures remain.
            ServiceUnavailableError: If prices are not configured, or EA is down.
        """
        season = self._season(season_id)
        pricing = self._pricing(self._open_config(season_id))
        if pricing.fixtures_remaining < 1:
            raise ForbiddenError("No fixtures remaining for this season.")
        if not pricing.junior_per_fixture and not pricing.adult_per_fixture:
            raise ServiceUnavailableError(
                "Entry prices have not been configured for this season. "
                "Please contact the league administrator."
            )
        entered = repository.get_entered_ea_urns(self._db, season_id, manager.club_id)
        choices = [
            self._choice(athlete, pricing.config.ea_reference_date, entered)
            for athlete in self._club_athletes(manager.club_id)
        ]
        choices.sort(key=lambda choice: (choice.already_entered, choice.athlete_name))
        return AthleteSelection(
            season=season,
            athletes=choices,
            junior_pence_per_fixture=pricing.junior_per_fixture,
            adult_pence_per_fixture=pricing.adult_per_fixture,
            junior_total_pence=pricing.amount_for(junior=True),
            adult_total_pence=pricing.amount_for(junior=False),
            fixtures_remaining=pricing.fixtures_remaining,
        )

    @staticmethod
    def _choice(
        athlete: EAAthlete, reference_date: date, entered: set[int]
    ) -> AthleteChoice:
        try:
            dob = athlete.parsed_date_of_birth()
        except ValueError:
            dob = None
        category = get_oxl_age_category(dob, reference_date) if dob else "Unknown"
        return AthleteChoice(
            ea_urn=athlete.individual_ref,
            athlete_name=athlete.full_name,
            date_of_birth=dob,
            ea_age_category=category,
            is_junior=is_junior(category),
            is_registered=athlete.is_registered,
            already_entered=athlete.individual_ref in entered,
        )

    def _entry_row(
        self,
        urn: int,
        athlete: EAAthlete | None,
        entered: set[int],
        pricing: _Pricing,
    ) -> AthleteEntryRow:
        if athlete is None:
            raise ValidationError(f"Athlete URN {urn} not found in EA.")
        if not athlete.is_registered:
            raise ValidationError(f"Athlete {urn} is not registered.")
        if urn in entered:
            raise ConflictError(f"Athlete {urn} already entered.")
        try:
            dob = athlete.parsed_date_of_birth()
        except ValueError as exc:
            raise ValidationError(f"Invalid DOB for athlete {urn}.") from exc
        if dob is None:
            raise ValidationError(f"Missing DOB for athlete {urn}.")
        category = get_oxl_age_category(dob, pricing.config.ea_reference_date)
        junior = is_junior(category)
        return AthleteEntryRow(
            ea_urn=urn,
            athlete_name=athlete.full_name,
            date_of_birth=dob,
            ea_age_category=category,
            is_junior=junior,
            amount_pence=pricing.amount_for(junior),
        )

    def create_batch(
        self, season_id: int, manager: ClubManager, user_id: int, ea_urns: list[int]
    ) -> EntryBatch:
        """Create a ``pending_payment`` batch after re-validating every athlete.

        Raises:
            NotFoundError: If the season does not exist.
            ForbiddenError: If entries are closed or the allocation is exceeded.
            ValidationError: If no or invalid athletes are selected.
            ConflictError: If an athlete is already entered.
        """
        self._season(season_id)
        config = self._open_config(season_id)
        if not ea_urns:
            raise ValidationError("No athletes selected.")
        pricing = self._pricing(config)
        by_urn = {a.individual_ref: a for a in self._club_athletes(manager.club_id)}
        entered = repository.get_entered_ea_urns(self._db, season_id, manager.club_id)
        rows = [
            self._entry_row(urn, by_urn.get(urn), entered, pricing) for urn in ea_urns
        ]
        if not self.check_allocation(season_id, manager.club_id, len(rows)):
            raise ForbiddenError(
                "Your club does not have enough allocation slots for this entry. "
                "Please contact the league administrator."
            )
        batch = repository.create_entry_batch(
            self._db,
            season_id=season_id,
            club_id=manager.club_id,
            manager_user_id=user_id,
            fixtures_remaining_at_entry=pricing.fixtures_remaining,
            total_pence=sum(row.amount_pence for row in rows),
        )
        repository.create_athlete_entries(
            self._db,
            batch_id=batch.id,
            season_id=season_id,
            club_id=manager.club_id,
            athletes=rows,
        )
        return batch

    def owned_batch(
        self, season_id: int, batch_id: int, manager: ClubManager
    ) -> EntryBatch:
        """Return a batch belonging to the manager's club in *season_id*.

        Raises:
            NotFoundError: If there is no such batch for this club and season.
        """
        batch = repository.get_entry_batch(self._db, batch_id)
        if (
            batch is None
            or batch.club_id != manager.club_id
            or batch.season_id != season_id
        ):
            raise NotFoundError
        return batch

    def season_and_batch(
        self, season_id: int, batch_id: int, manager: ClubManager
    ) -> tuple[Season, EntryBatch]:
        """Return the season and an owned batch.

        Raises:
            NotFoundError: If the season or batch does not exist for this club.
        """
        return self._season(season_id), self.owned_batch(season_id, batch_id, manager)

    def preview(
        self, season_id: int, batch_id: int, manager: ClubManager
    ) -> BatchPreview:
        """Summarise an owned batch for the pre-payment review page.

        Raises:
            NotFoundError: If the season or batch does not exist for this club.
        """
        season, batch = self.season_and_batch(season_id, batch_id, manager)
        athletes = repository.get_athlete_entries_for_batch(self._db, batch_id)
        juniors = [a for a in athletes if a.is_junior]
        adults = [a for a in athletes if not a.is_junior]
        return BatchPreview(
            season=season,
            batch=batch,
            athletes=athletes,
            junior_count=len(juniors),
            adult_count=len(adults),
            junior_total=sum(a.amount_pence for a in juniors),
            adult_total=sum(a.amount_pence for a in adults),
        )

    def start_checkout(
        self,
        season_id: int,
        batch_id: int,
        manager: ClubManager,
        user_id: int,
        base_url: str,
    ) -> CheckoutOutcome:
        """Create a hosted checkout for an unpaid batch.

        Raises:
            NotFoundError: If the season or batch does not exist for this club.
            ServiceUnavailableError: If payments are not configured.
        """
        season, batch = self.season_and_batch(season_id, batch_id, manager)
        batch_path = f"/entries/{season_id}/batch/{batch_id}"
        if batch.status not in PAYABLE_STATUSES:
            return CheckoutOutcome(url=f"{batch_path}/success", started=False)
        athletes = repository.get_athlete_entries_for_batch(self._db, batch_id)
        juniors = [a for a in athletes if a.is_junior]
        adults = [a for a in athletes if not a.is_junior]
        checkout = self._payments.create_checkout_session(
            CheckoutRequest(
                batch_id=batch_id,
                junior_count=len(juniors),
                junior_unit_pence=juniors[0].amount_pence if juniors else 0,
                adult_count=len(adults),
                adult_unit_pence=adults[0].amount_pence if adults else 0,
                club_name=manager.club_name,
                season_name=season.name,
                manager_email=repository.get_club_manager_email(self._db, user_id),
                success_url=f"{base_url}{batch_path}/success",
                cancel_url=f"{base_url}{batch_path}/preview",
            )
        )
        repository.set_batch_stripe_session(
            self._db, batch_id=batch_id, session_id=checkout.session_id
        )
        return CheckoutOutcome(url=checkout.url, started=True)

    # -- receipts and overview -------------------------------------------------

    def receipt_for_manager(
        self, season_id: int, batch_id: int, manager: ClubManager
    ) -> Receipt:
        """Return the receipt of an owned, paid batch.

        Raises:
            NotFoundError: If the batch does not exist for this club.
            ForbiddenError: If the batch has not been paid.
        """
        batch = self.owned_batch(season_id, batch_id, manager)
        if not batch.is_paid:
            raise ForbiddenError("Receipt is only available after payment.")
        return self.receipt(batch_id)

    def receipt(self, batch_id: int) -> Receipt:
        """Return the receipt of a paid batch.

        Raises:
            NotFoundError: If the batch does not exist or is not paid.
        """
        db = self._db
        batch = found(repository.get_entry_batch(db, batch_id), "Entry batch not found")
        if not batch.is_paid:
            raise NotFoundError("Receipt not available")
        club = repository.get_club_by_id(db, batch.club_id)
        manager = repository.get_user_by_id(db, batch.manager_user_id)
        season = repository.get_season_by_id(db, batch.season_id)
        return _receipt_from(
            batch,
            repository.get_athlete_entries_for_batch(db, batch_id),
            club.name if club else None,
            manager.username if manager else None,
            season.name if season else None,
        )

    def season_entries(self, season_id: int) -> SeasonEntries:
        """Return every club's paid entries for a season.

        Raises:
            NotFoundError: If the season does not exist.
        """
        season = self._season(season_id)
        by_club: dict[str, list[AthleteEntryListing]] = {}
        for entry in repository.list_athlete_entries_for_season(self._db, season_id):
            by_club.setdefault(entry.club_name, []).append(entry)
        config = repository.get_season_entry_config(self._db, season_id)
        entries_open = bool(config and config.entries_open)
        can_add_more = entries_open and self.fixtures_remaining(season_id) > 0
        return SeasonEntries(
            season=season, entries_by_club=by_club, can_add_more=can_add_more
        )
