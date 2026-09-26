"""Route tests: the Stripe webhook endpoint."""

from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

from website import repository
from website.errors import InvalidRequestError
from website.models import UserRole

_VERIFY = "website.web.routes.webhooks.verify_webhook"


def _batch_with_session(db: duckdb.DuckDBPyConnection) -> int:
    season = repository.create_season(db, "Webhook Season")
    club = repository.create_club(db, name="Hook AC", oxl_code="HAC", ea_club_id="7")
    user = repository.create_user(db, "hook", "hash", UserRole.club_manager)
    batch = repository.create_entry_batch(
        db,
        season_id=season.id,
        club_id=club.id,
        manager_user_id=user.id,
        fixtures_remaining_at_entry=2,
        total_pence=500,
    )
    repository.set_batch_stripe_session(db, batch_id=batch.id, session_id="cs_hook")
    return batch.id


class TestStripeWebhook:
    def test_completed_checkout_marks_batch_paid(
        self, test_client: TestClient, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        batch_id = _batch_with_session(test_db)
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_hook",
                    "payment_intent": "pi_hook",
                    "payment_status": "paid",
                    "payment_method_types": ["card"],
                }
            },
        }
        with patch(_VERIFY, return_value=event):
            resp = test_client.post(
                "/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"}
            )
        assert resp.status_code == 200
        batch = repository.get_entry_batch(test_db, batch_id)
        assert batch is not None
        assert batch.status == "paid"

    def test_unhandled_event_types_are_acknowledged(
        self, test_client: TestClient
    ) -> None:
        with patch(_VERIFY, return_value={"type": "invoice.paid", "data": {}}):
            resp = test_client.post("/webhooks/stripe", content=b"{}")
        assert resp.status_code == 200

    def test_bad_signature_is_rejected(self, test_client: TestClient) -> None:
        with patch(
            _VERIFY, side_effect=InvalidRequestError("Invalid Stripe signature")
        ):
            resp = test_client.post("/webhooks/stripe", content=b"{}")
        assert resp.status_code == 400
        assert resp.json() == {"detail": "Invalid Stripe signature"}
