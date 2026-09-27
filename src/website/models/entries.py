"""Team entries: configuration, batches, athlete entries and allocations."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

PAID_STATUSES = ("paid", "payment_initiated")
PAYABLE_STATUSES = ("pending_payment", "payment_failed")


class AthleteEntryRow(BaseModel):
    """An athlete included in an entry batch."""

    model_config = ConfigDict(frozen=True)

    ea_urn: int
    athlete_name: str
    date_of_birth: date
    ea_age_category: str
    is_junior: bool
    amount_pence: int
    race_number: int | None = None


class EntryBatch(BaseModel):
    """A club's paid (or pending) set of athlete entries for a season."""

    model_config = ConfigDict(frozen=True)

    id: int
    season_id: int
    club_id: int
    manager_user_id: int
    status: str
    fixtures_remaining_at_entry: int
    total_pence: int
    stripe_checkout_session_id: str | None
    stripe_payment_intent_id: str | None
    stripe_payment_method: str | None
    paid_at: datetime | None
    created_at: datetime

    @property
    def is_paid(self) -> bool:
        """Return True once payment has completed or been initiated."""
        return self.status in PAID_STATUSES


class EntryBatchSummary(BaseModel):
    """An entry batch joined with club and manager names, for admin lists."""

    model_config = ConfigDict(frozen=True)

    id: int
    club_id: int
    club_name: str
    manager_username: str
    status: str
    fixtures_remaining_at_entry: int
    total_pence: int
    stripe_payment_method: str | None
    paid_at: datetime | None
    created_at: datetime
    season_id: int
    season_name: str = "?"


class SeasonEntryConfig(BaseModel):
    """Entry settings and pricing for a season."""

    model_config = ConfigDict(frozen=True)

    season_id: int
    entries_open: bool
    ea_reference_date: date
    total_fixtures: int
    junior_pence_per_fixture: int | None = None
    adult_pence_per_fixture: int | None = None


class AthleteEntryListing(BaseModel):
    """A paid athlete entry shown in the season overview."""

    model_config = ConfigDict(frozen=True)

    ea_urn: int
    athlete_name: str
    ea_age_category: str
    race_number: int | None
    club_name: str
    club_id: int


class ClubAllocationRow(BaseModel):
    """A club's entry allocation and usage for a season."""

    model_config = ConfigDict(frozen=True)

    club_id: int
    club_name: str
    allocated_slots: int
    current_used: int
    remaining: int


class PaidAthleteEntry(BaseModel):
    """A paid athlete entry for reporting."""

    model_config = ConfigDict(frozen=True)

    athlete_id: int
    club_name: str
    athlete_name: str
    age_category: str
    date_of_birth: date
    ea_urn: int
    race_number: int | None


class EAAthlete(BaseModel):
    """An England Athletics athlete record, keyed as the TRAPI API returns it."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    individual_ref: int = Field(default=0, alias="IndividualRef")
    first_name: str = Field(default="", alias="FirstName")
    last_name: str = Field(default="", alias="LastName")
    date_of_birth: str | None = Field(default=None, alias="DateOfBirth")
    registration_status: str = Field(default="", alias="RegistrationStatus")

    @property
    def full_name(self) -> str:
        """Return the athlete's display name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_registered(self) -> bool:
        """Return True if the athlete holds a current competitive registration."""
        return self.registration_status == "Registered"

    def parsed_date_of_birth(self) -> date | None:
        """Return the date of birth, or None when missing.

        Raises:
            ValueError: If a date of birth is present but not an ISO date.
        """
        if not self.date_of_birth:
            return None
        return date.fromisoformat(str(self.date_of_birth)[:10])


class AthleteChoice(BaseModel):
    """An athlete row on the entry selection form."""

    model_config = ConfigDict(frozen=True)

    ea_urn: int
    athlete_name: str
    date_of_birth: date | None
    ea_age_category: str
    is_junior: bool
    is_registered: bool
    already_entered: bool
