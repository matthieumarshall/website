"""Stripe Checkout Session creation and webhook signature verification."""

import os
from typing import Any, NamedTuple, cast

import stripe
from fastapi import HTTPException, Request


def _get_stripe_client() -> stripe.StripeClient:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
    return stripe.StripeClient(secret_key)


class CheckoutSession(NamedTuple):
    url: str
    session_id: str


def create_checkout_session(
    batch_id: int,
    junior_count: int,
    junior_unit_pence: int,
    adult_count: int,
    adult_unit_pence: int,
    club_name: str,
    season_name: str,
    manager_email: str | None,
    success_url: str,
    cancel_url: str,
) -> CheckoutSession:
    """Create a Stripe Checkout Session and return (url, session_id).

    Supports card and BACS Direct Debit (GBP only).
    """
    client = _get_stripe_client()
    line_items = []
    if junior_count > 0:
        line_items.append(
            {
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": f"Junior entry \u00d7 {junior_count} \u2014 {club_name}",
                        "description": f"Season: {season_name}",
                    },
                    "unit_amount": junior_unit_pence,
                },
                "quantity": junior_count,
            }
        )
    if adult_count > 0:
        line_items.append(
            {
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": f"Adult entry \u00d7 {adult_count} \u2014 {club_name}",
                        "description": f"Season: {season_name}",
                    },
                    "unit_amount": adult_unit_pence,
                },
                "quantity": adult_count,
            }
        )
    params_dict: Any = {  # typed as Any — Stripe SDK expects SessionCreateParams TypedDict
        "payment_method_types": ["card", "bacs_debit"],
        "line_items": line_items,
        "mode": "payment",
        "currency": "gbp",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"batch_id": str(batch_id)},
    }
    if manager_email:
        params_dict["customer_email"] = manager_email
    session = client.checkout.sessions.create(params=cast(Any, params_dict))
    session_url: str = session.url or ""
    return CheckoutSession(url=session_url, session_id=session.id)


async def verify_webhook(request: Request) -> stripe.Event:
    """Verify the Stripe-Signature header and construct the event.

    Must receive the raw request body (bytes) — call before any body parsing.
    Raises HTTPException(400) on invalid signature.
    """
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    sig_header = request.headers.get("stripe-signature", "")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc
    return event
