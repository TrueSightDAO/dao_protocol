"""`POST /stripe/subscription_webhook` — Stripe subscription webhook handler.

Handles Stripe test webhook events for subscription lifecycle:
- ``checkout.session.completed`` — write a row to the SANDBOX fulfillment-queue sheet
- ``invoice.paid`` — idempotent on invoice ID, write/update the SANDBOX row
- ``invoice.payment_failed`` — mark the row as failed
- ``customer.subscription.deleted`` — mark the row as cancelled

Returns 200 to Stripe promptly (ack the webhook). Returns 400 for unverified signatures.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..services.sandbox_sheet import (
    mark_subscription_cancelled,
    mark_subscription_failed,
    write_subscription_row,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/stripe/subscription_webhook")
async def stripe_subscription_webhook(request: Request) -> Response:
    settings = get_settings()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        return JSONResponse({"status": "error", "error": "missing stripe-signature header"}, status_code=400)

    try:
        import stripe

        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
    except ValueError:
        return JSONResponse({"status": "error", "error": "invalid payload"}, status_code=400)
    except stripe.error.SignatureVerificationError:
        return JSONResponse({"status": "error", "error": "invalid signature"}, status_code=400)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        customer_email = data.get("customer_details", {}).get("email", "") or data.get("customer_email", "")
        subscription_id = data.get("subscription", "")
        invoice_id = data.get("invoice", "")
        if subscription_id:
            write_subscription_row(
                customer_email=customer_email,
                subscription_id=subscription_id,
                invoice_id=invoice_id,
                status="active",
            )

    elif event_type == "invoice.paid":
        subscription_id = data.get("subscription", "")
        invoice_id = data.get("id", "")
        customer_email = data.get("customer_email", "") or data.get("customer", "")
        if subscription_id:
            write_subscription_row(
                customer_email=customer_email,
                subscription_id=subscription_id,
                invoice_id=invoice_id,
                status="active",
            )

    elif event_type == "invoice.payment_failed":
        subscription_id = data.get("subscription", "")
        invoice_id = data.get("id", "")
        if subscription_id:
            mark_subscription_failed(subscription_id=subscription_id, invoice_id=invoice_id)

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id", "")
        if subscription_id:
            mark_subscription_cancelled(subscription_id=subscription_id)

    else:
        logger.info("Unhandled event type: %s", event_type)

    return Response(status_code=200)
