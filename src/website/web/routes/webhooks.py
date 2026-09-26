"""Stripe webhooks (no CSRF: the raw body's signature is verified instead)."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from website.integrations.stripe_payments import verify_webhook
from website.services.entry_admin import WebhookEvent
from website.web.deps import EntryAdmin

router = APIRouter()
HANDLED_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    }
)


def _to_event(event_type: str, session: Any) -> WebhookEvent:  # noqa: ANN401 — Stripe object
    return WebhookEvent(
        type=event_type,
        session_id=session["id"],
        payment_intent=session.get("payment_intent"),
        payment_status=session.get("payment_status"),
        payment_method_types=session.get("payment_method_types") or [],
    )


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, service: EntryAdmin) -> Response:
    """Record Checkout payment outcomes against entry batches."""
    event = verify_webhook(
        await request.body(), request.headers.get("stripe-signature", "")
    )
    event_type: str = event["type"]
    if event_type in HANDLED_EVENTS:
        service.apply_payment_event(_to_event(event_type, event["data"]["object"]))
    return Response(status_code=200)
