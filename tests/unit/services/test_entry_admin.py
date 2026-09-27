"""EntryAdminService: overview filtering, pricing config and payment events."""

from datetime import date

import duckdb
import pytest

from website import repository
from website.errors import NotFoundError, ValidationError
from website.models import AthleteEntryRow, UserRole
from website.models.forms import EntryConfigForm
from website.services.entry_admin import EntryAdminService, WebhookEvent


def _seed_batch(db: duckdb.DuckDBPyConnection, session_id: str = "cs_1") -> int:
    season = repository.create_season(db, "2025-26")
    club = repository.create_club(db, name="Oxford AC", oxl_code="OXA", ea_club_id="1")
    user = repository.create_user(db, "mgr", "hash", UserRole.club_manager)
    batch = repository.create_entry_batch(
        db,
        season_id=season.id,
        club_id=club.id,
        manager_user_id=user.id,
        fixtures_remaining_at_entry=3,
        total_pence=900,
    )
    # Set the session first: DuckDB rejects updates to this indexed column once
    # athlete_entries reference the batch (see the checkout follow-up issue).
    repository.set_batch_stripe_session(db, batch_id=batch.id, session_id=session_id)
    repository.create_athlete_entries(
        db,
        batch_id=batch.id,
        season_id=season.id,
        club_id=club.id,
        athletes=[
            AthleteEntryRow(
                ea_urn=urn,
                athlete_name=f"Runner {urn}",
                date_of_birth=date(2010, 1, 1),
                ea_age_category="U17",
                is_junior=True,
                amount_pence=450,
            )
            for urn in (1, 2)
        ],
    )
    return batch.id


def _race_numbers(db: duckdb.DuckDBPyConnection, batch_id: int) -> list[int | None]:
    return [
        entry.race_number
        for entry in repository.get_athlete_entries_for_batch(db, batch_id)
    ]


class TestPaymentEvents:
    def test_completed_paid_session_marks_batch_paid_and_numbers_athletes(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        batch_id = _seed_batch(test_db)
        EntryAdminService(test_db).apply_payment_event(
            WebhookEvent(
                type="checkout.session.completed",
                session_id="cs_1",
                payment_intent="pi_1",
                payment_status="paid",
                payment_method_types=["card"],
            )
        )
        batch = repository.get_entry_batch(test_db, batch_id)
        assert batch is not None
        assert batch.status == "paid"
        assert batch.stripe_payment_intent_id == "pi_1"
        assert batch.paid_at is not None
        assert _race_numbers(test_db, batch_id) == [1, 2]

    def test_completed_unpaid_session_is_payment_initiated(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        batch_id = _seed_batch(test_db)
        EntryAdminService(test_db).apply_payment_event(
            WebhookEvent(
                type="checkout.session.completed",
                session_id="cs_1",
                payment_status="unpaid",
                payment_method_types=["bacs_debit"],
            )
        )
        batch = repository.get_entry_batch(test_db, batch_id)
        assert batch is not None
        assert batch.status == "payment_initiated"
        assert batch.stripe_payment_method == "bacs_debit"
        assert _race_numbers(test_db, batch_id) == [None, None]

    def test_async_success_then_failure(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        batch_id = _seed_batch(test_db)
        service = EntryAdminService(test_db)
        service.apply_payment_event(
            WebhookEvent(
                type="checkout.session.async_payment_succeeded", session_id="cs_1"
            )
        )
        batch = repository.get_entry_batch(test_db, batch_id)
        assert batch is not None
        assert batch.status == "paid"
        service.apply_payment_event(
            WebhookEvent(
                type="checkout.session.async_payment_failed", session_id="cs_1"
            )
        )
        batch = repository.get_entry_batch(test_db, batch_id)
        assert batch is not None
        assert batch.status == "payment_failed"

    def test_unknown_session_is_ignored(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        EntryAdminService(test_db).apply_payment_event(
            WebhookEvent(type="checkout.session.completed", session_id="cs_missing")
        )


class TestConfigAndOverview:
    def test_save_config_converts_pounds_to_pence(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2026-27")
        EntryAdminService(test_db).save_config(
            season.id,
            EntryConfigForm(
                entries_open=True,
                ea_reference_date="2026-08-31",
                total_fixtures=5,
                junior_pence_per_fixture_display=2.5,
                adult_pence_per_fixture_display=4,
            ),
        )
        config = repository.get_season_entry_config(test_db, season.id)
        assert config is not None
        assert config.entries_open is True
        assert config.junior_pence_per_fixture == 250
        assert config.adult_pence_per_fixture == 400

    def test_save_config_rejects_negative_prices(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        season = repository.create_season(test_db, "2027-28")
        form = EntryConfigForm(
            ea_reference_date="2027-08-31",
            total_fixtures=5,
            junior_pence_per_fixture_display=-1,
        )
        with pytest.raises(ValidationError):
            EntryAdminService(test_db).save_config(season.id, form)

    def test_season_view_requires_existing_season(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        with pytest.raises(NotFoundError):
            EntryAdminService(test_db).season(999)

    def test_overview_labels_batches_with_season_names(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        _seed_batch(test_db)
        overview = EntryAdminService(test_db).overview(season_id=None, status=None)
        assert [batch.season_name for batch in overview.batches] == ["2025-26"]
        filtered = EntryAdminService(test_db).overview(season_id=None, status="paid")
        assert filtered.batches == []
