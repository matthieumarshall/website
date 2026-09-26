"""Stripe Checkout Session creation and webhook signature verification."""

import os
from functools import lru_cache
from typing import Any, NamedTuple, Protocol, cast

import stripe
from pydantic import BaseModel, ConfigDict

from website.errors import InvalidRequestError, ServiceUnavailableError


class CheckoutSession(NamedTuple):
    """The hosted checkout page URL and its Stripe session id."""

    url: str
    session_id: str


class CheckoutRequest(BaseModel):
    """Everything needed to create a Checkout Session for an entry batch."""

    model_config = ConfigDict(frozen=True)

    batch_id: int
    junior_count: int
    junior_unit_pence: int
    adult_count: int
    adult_unit_pence: int
    club_name: str
    season_name: str
    manager_email: str | None
    success_url: str
    cancel_url: str


class PaymentGateway(Protocol):
    """Anything that can start a hosted payment for an entry batch."""

    def create_checkout_session(self, request: CheckoutRequest) -> CheckoutSession:
        """Create a hosted checkout session."""
        ...


def _get_stripe_secret_key() -> str:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise ServiceUnavailableError(
            "Stripe is not configured. Contact the league administrator."
        )
    return secret_key


@lru_cache(maxsize=4)
def _build_stripe_client(secret_key: str) -> stripe.StripeClient:
    """Return a memoized Stripe client for the given secret key."""
    return stripe.StripeClient(secret_key)


def _get_stripe_client() -> stripe.StripeClient:
    """Return a cached Stripe client and rebuild only when the key changes."""
    return _build_stripe_client(_get_stripe_secret_key())


def _line_item(
    label: str, count: int, unit_pence: int, request: CheckoutRequest
) -> dict[str, object]:
    return {
        "price_data": {
            "currency": "gbp",
            "product_data": {
                "name": f"{label} entry × {count} — {request.club_name}",
                "description": f"Season: {request.season_name}",
            },
            "unit_amount": unit_pence,
        },
        "quantity": count,
    }


def create_checkout_session(request: CheckoutRequest) -> CheckoutSession:
    """Create a Stripe Checkout Session (card and BACS Direct Debit, GBP).

    Raises:
        ServiceUnavailableError: If Stripe is not configured.
    """
    client = _get_stripe_client()
    line_items: list[dict[str, object]] = []
    if request.junior_count > 0:
        line_items.append(
            _line_item(
                "Junior", request.junior_count, request.junior_unit_pence, request
            )
        )
    if request.adult_count > 0:
        line_items.append(
            _line_item("Adult", request.adult_count, request.adult_unit_pence, request)
        )
    params: dict[str, object] = {
        "payment_method_types": ["card", "bacs_debit"],
        "line_items": line_items,
        "mode": "payment",
        "currency": "gbp",
        "success_url": request.success_url,
        "cancel_url": request.cancel_url,
        "metadata": {"batch_id": str(request.batch_id)},
    }
    if request.manager_email:
        params["customer_email"] = request.manager_email
    # The SDK expects a SessionCreateParams TypedDict; the dict above matches it.
    session = client.checkout.sessions.create(params=cast(Any, params))
    return CheckoutSession(url=session.url or "", session_id=session.id)


class StripeGateway:
    """:class:`PaymentGateway` backed by Stripe Checkout."""

    def create_checkout_session(self, request: CheckoutRequest) -> CheckoutSession:
        """Create a hosted Stripe Checkout session."""
        return create_checkout_session(request)


def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify a webhook's ``Stripe-Signature`` header and construct the event.

    Raises:
        InvalidRequestError: If the signature is invalid.
    """
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.SignatureVerificationError as exc:
        raise InvalidRequestError("Invalid Stripe signature") from exc
