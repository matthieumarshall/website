"""Unit tests for website.payments — webhook verification and CheckoutSession."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from website.payments import CheckoutSession, verify_webhook


# ---------------------------------------------------------------------------
# verify_webhook
# ---------------------------------------------------------------------------


class TestVerifyWebhook:
    @pytest.mark.asyncio
    async def test_valid_signature_returns_event(self):
        """A valid signature should return the Stripe Event object."""
        fake_payload = b'{"type": "checkout.session.completed", "id": "evt_test"}'
        fake_event = MagicMock(spec=stripe.Event)
        fake_event.type = "checkout.session.completed"

        request = MagicMock()
        request.headers = {"stripe-signature": "t=123,v1=abc"}
        request.body = AsyncMock(return_value=fake_payload)

        with patch(
            "website.payments.stripe.Webhook.construct_event", return_value=fake_event
        ):
            result = await verify_webhook(request)

        assert result is fake_event

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_http_400(self):
        """An invalid signature should raise HTTPException with status 400."""
        from fastapi import HTTPException

        fake_payload = b'{"type": "checkout.session.completed"}'
        request = MagicMock()
        request.headers = {"stripe-signature": "t=123,v1=bad"}
        request.body = AsyncMock(return_value=fake_payload)

        with patch(
            "website.payments.stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError(
                "bad sig", sig_header="t=123,v1=bad"
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_webhook(request)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_signature_header_raises_400(self):
        """A missing Stripe-Signature header should still raise 400."""
        from fastapi import HTTPException

        fake_payload = b'{"type": "checkout.session.completed"}'
        request = MagicMock()
        request.headers = {}  # no stripe-signature
        request.body = AsyncMock(return_value=fake_payload)

        with patch(
            "website.payments.stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError("no sig", sig_header=""),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_webhook(request)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# CheckoutSession NamedTuple
# ---------------------------------------------------------------------------


class TestCheckoutSession:
    def test_fields_accessible_by_name(self):
        cs = CheckoutSession(url="https://pay.stripe.com/test", session_id="cs_abc")
        assert cs.url == "https://pay.stripe.com/test"
        assert cs.session_id == "cs_abc"

    def test_is_namedtuple(self):
        cs = CheckoutSession(url="https://x.com", session_id="y")
        assert isinstance(cs, tuple)
        assert cs[0] == "https://x.com"
        assert cs[1] == "y"
