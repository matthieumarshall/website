"""Unit tests for the Stripe integration — webhook verification and checkout."""

import os
from unittest.mock import MagicMock, patch

import pytest
import stripe

from website.errors import InvalidRequestError, ServiceUnavailableError
from website.integrations import stripe_payments as payments
from website.integrations.stripe_payments import (
    CheckoutRequest,
    CheckoutSession,
    create_checkout_session,
    verify_webhook,
)

_CONSTRUCT_EVENT = "website.integrations.stripe_payments.stripe.Webhook.construct_event"
_STRIPE_CLIENT = "website.integrations.stripe_payments.stripe.StripeClient"


# ---------------------------------------------------------------------------
# verify_webhook
# ---------------------------------------------------------------------------


class TestVerifyWebhook:
    def test_valid_signature_returns_event(self) -> None:
        """A valid signature should return the Stripe Event object."""
        fake_payload = b'{"type": "checkout.session.completed", "id": "evt_test"}'
        fake_event = MagicMock(spec=stripe.Event)
        fake_event.type = "checkout.session.completed"

        with patch(_CONSTRUCT_EVENT, return_value=fake_event):
            result = verify_webhook(fake_payload, "t=123,v1=abc")

        assert result is fake_event

    def test_invalid_signature_raises_invalid_request(self) -> None:
        """An invalid signature is rejected (mapped to HTTP 400)."""
        with (
            patch(
                _CONSTRUCT_EVENT,
                side_effect=stripe.SignatureVerificationError(
                    "bad sig", sig_header="t=123,v1=bad"
                ),
            ),
            pytest.raises(InvalidRequestError),
        ):
            verify_webhook(b'{"type": "checkout.session.completed"}', "t=123,v1=bad")

    def test_missing_signature_header_is_rejected(self) -> None:
        """A missing Stripe-Signature header is rejected too."""
        with (
            patch(
                _CONSTRUCT_EVENT,
                side_effect=stripe.SignatureVerificationError("no sig", sig_header=""),
            ),
            pytest.raises(InvalidRequestError),
        ):
            verify_webhook(b'{"type": "checkout.session.completed"}', "")


# ---------------------------------------------------------------------------
# CheckoutSession NamedTuple
# ---------------------------------------------------------------------------


class TestCheckoutSession:
    def test_fields_accessible_by_name(self) -> None:
        cs = CheckoutSession(url="https://pay.stripe.com/test", session_id="cs_abc")
        assert cs.url == "https://pay.stripe.com/test"
        assert cs.session_id == "cs_abc"

    def test_is_namedtuple(self) -> None:
        cs = CheckoutSession(url="https://x.com", session_id="y")
        assert isinstance(cs, tuple)
        assert cs[0] == "https://x.com"
        assert cs[1] == "y"


class TestCreateCheckoutSession:
    def teardown_method(self) -> None:
        payments._build_stripe_client.cache_clear()

    def test_builds_line_items_for_juniors_and_adults(self) -> None:
        client = MagicMock()
        client.checkout.sessions.create.return_value = MagicMock(
            url="https://checkout.test/cs_1", id="cs_1"
        )
        request = CheckoutRequest(
            batch_id=7,
            junior_count=2,
            junior_unit_pence=500,
            adult_count=1,
            adult_unit_pence=900,
            club_name="Oxford City AC",
            season_name="2025-26",
            manager_email="manager@example.com",
            success_url="https://site/success",
            cancel_url="https://site/cancel",
        )
        with (
            patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_line_items"}),
            patch(_STRIPE_CLIENT, return_value=client),
        ):
            session = create_checkout_session(request)

        assert session == CheckoutSession(
            url="https://checkout.test/cs_1", session_id="cs_1"
        )
        params = client.checkout.sessions.create.call_args.kwargs["params"]
        assert [item["quantity"] for item in params["line_items"]] == [2, 1]
        assert params["customer_email"] == "manager@example.com"
        assert params["metadata"] == {"batch_id": "7"}


class TestStripeClientCaching:
    def teardown_method(self) -> None:
        # Isolate tests from one another by clearing the LRU cache.
        payments._build_stripe_client.cache_clear()

    def test_get_stripe_client_reuses_cached_client(self) -> None:
        with (
            patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_cached"}),
            patch(_STRIPE_CLIENT) as mock_ctor,
        ):
            client_1 = payments._get_stripe_client()
            client_2 = payments._get_stripe_client()

        assert mock_ctor.call_count == 1
        assert client_1 is client_2

    def test_get_stripe_client_rebuilds_when_key_changes(self) -> None:
        first_client = MagicMock(name="first_client")
        second_client = MagicMock(name="second_client")
        with patch(
            _STRIPE_CLIENT, side_effect=[first_client, second_client]
        ) as mock_ctor:
            with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_first"}):
                client_1 = payments._get_stripe_client()

            with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_second"}):
                client_2 = payments._get_stripe_client()

        assert mock_ctor.call_count == 2
        assert client_1 is not client_2

    def test_get_stripe_client_unavailable_when_key_missing(self) -> None:
        with (
            patch.dict(os.environ, {"STRIPE_SECRET_KEY": ""}),
            pytest.raises(ServiceUnavailableError),
        ):
            payments._get_stripe_client()
