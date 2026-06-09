"""`POST /subscription/obligation` — create a PENDING fulfillment obligation.

Called by the Rails webhook (`sentiment_importer`) when an Agroverse subscription
invoice is paid (first charge via `checkout.session.completed` or renewal via
`invoice.payment_succeeded`). Retrieves the subscription + invoice from Stripe,
extracts subscriber info, and appends to the Subscription Fulfillment Queue.

Accepts query params: `subscription_id` (required), `invoice_id` (optional),
`session_id` (optional, for first-charge lookups).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..sheets import subscription_fulfillment_queue as queue
from ..services import stripe_client

router = APIRouter()


@router.post("/subscription/obligation")
async def subscription_obligation(request: Request) -> JSONResponse:
    subscription_id = (request.query_params.get("subscription_id") or "").strip()
    invoice_id = (request.query_params.get("invoice_id") or "").strip()
    session_id = (request.query_params.get("session_id") or "").strip()

    if not subscription_id:
        try:
            form = await request.form()
            subscription_id = str(form.get("subscription_id") or "").strip()
            invoice_id = invoice_id or str(form.get("invoice_id") or "").strip()
            session_id = session_id or str(form.get("session_id") or "").strip()
        except Exception:
            pass

    if not subscription_id:
        return JSONResponse(
            {"status": "error", "error": "subscription_id required"},
            status_code=400,
        )

    try:
        result = _create_obligation(subscription_id, invoice_id, session_id)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)


def _create_obligation(
    subscription_id: str,
    invoice_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Create a PENDING fulfillment obligation from a Stripe subscription."""
    # Retrieve the subscription from Stripe
    sub = stripe_client.retrieve_subscription(subscription_id)
    if sub is None:
        return {"status": "error", "error": "Subscription not found in Stripe"}

    # Get the latest invoice (or use the provided invoice_id)
    target_invoice_id = invoice_id or getattr(sub, "latest_invoice", None)
    if isinstance(target_invoice_id, str) and target_invoice_id:
        pass  # Already have it
    else:
        target_invoice_id = getattr(sub, "latest_invoice", None) or ""
        if hasattr(target_invoice_id, "id"):
            target_invoice_id = target_invoice_id.id

    # If we still don't have an invoice_id, try to get it from the session
    if not target_invoice_id and session_id:
        session = stripe_client.retrieve_session_full(session_id)
        if session:
            target_invoice_id = getattr(session, "invoice", None) or ""
            if hasattr(target_invoice_id, "id"):
                target_invoice_id = target_invoice_id.id

    # Check idempotency — if we have an invoice_id, check if it already exists
    if target_invoice_id and queue.record_exists(str(target_invoice_id)):
        return {"status": "already_exists", "invoice_id": str(target_invoice_id)}

    # Extract subscriber info from the subscription
    metadata = getattr(sub, "metadata", None) or {}
    if hasattr(metadata, "get"):
        metadata = metadata
    else:
        metadata = {}

    # Get customer details
    customer_id = getattr(sub, "customer", None) or ""
    if hasattr(customer_id, "id"):
        customer_id = customer_id.id

    customer = stripe_client.retrieve_customer(str(customer_id)) if customer_id else None

    subscriber_name = ""
    email = ""
    address = ""

    if customer:
        subscriber_name = getattr(customer, "name", None) or ""
        email = getattr(customer, "email", None) or ""
        addr = getattr(customer, "address", None) or {}
        if hasattr(addr, "get"):
            addr = addr
        else:
            addr = {}
        address_parts = []
        if addr.get("line1"):
            address_parts.append(addr["line1"])
        if addr.get("line2"):
            address_parts.append(addr["line2"])
        if addr.get("city"):
            address_parts.append(addr["city"])
        if addr.get("state"):
            address_parts.append(addr["state"])
        if addr.get("postal_code"):
            address_parts.append(addr["postal_code"])
        if addr.get("country"):
            address_parts.append(addr["country"])
        address = ", ".join(address_parts)

    # Fall back to metadata if customer info is missing
    if not subscriber_name:
        subscriber_name = metadata.get("shippingName", "") or \
                          metadata.get("shipping_name", "") or ""
    if not email:
        email = metadata.get("customer_email", "") or ""
    if not address:
        addr_parts = []
        if metadata.get("shippingAddress"):
            addr_parts.append(str(metadata["shippingAddress"]))
        if metadata.get("shippingCity"):
            addr_parts.append(str(metadata["shippingCity"]))
        if metadata.get("shippingState"):
            addr_parts.append(str(metadata["shippingState"]))
        if metadata.get("shippingZip"):
            addr_parts.append(str(metadata["shippingZip"]))
        if metadata.get("shippingCountry"):
            addr_parts.append(str(metadata["shippingCountry"]))
        address = ", ".join(addr_parts)

    # Extract SKU and quantity from subscription items
    items = getattr(sub, "items", None) or {}
    data = getattr(items, "data", None) or []

    sku = metadata.get("sku", "") or "generic-ceremonial-cacao-chocolate-bar"
    qty = 6  # Default

    for item in data:
        price = getattr(item, "price", None) or {}
        if hasattr(price, "get"):
            price = price
        else:
            price = {}
        product_data = price.get("product", {}) if isinstance(price, dict) else {}
        if hasattr(product_data, "get"):
            product_data = product_data
        else:
            product_data = {}
        item_metadata = getattr(item, "metadata", None) or {}
        if hasattr(item_metadata, "get"):
            item_metadata = item_metadata
        else:
            item_metadata = {}

        # Try to get quantity from the subscription item
        item_qty = getattr(item, "quantity", None) or 0
        if item_qty:
            qty = int(item_qty)

        # Try to get SKU from product metadata
        if isinstance(product_data, dict) and product_data.get("metadata"):
            pm = product_data["metadata"]
            if isinstance(pm, dict) and pm.get("sku"):
                sku = pm["sku"]

    # Override from metadata if set
    qty_meta = metadata.get("quantity", "")
    if qty_meta:
        try:
            qty = int(str(qty_meta))
        except (ValueError, TypeError):
            pass

    # Calculate period dates
    current_period_start = getattr(sub, "current_period_start", None)
    current_period_end = getattr(sub, "current_period_end", None)

    period_start = ""
    period_end = ""
    if current_period_start:
        try:
            period_start = datetime.fromtimestamp(
                int(current_period_start), tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            period_start = str(current_period_start)
    if current_period_end:
        try:
            period_end = datetime.fromtimestamp(
                int(current_period_end), tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            period_end = str(current_period_end)

    # Use the invoice_id we resolved (or a fallback)
    final_invoice_id = str(target_invoice_id or f"sub_{subscription_id}")

    # Append to the queue
    ok = queue.append_obligation(
        subscriber_name=str(subscriber_name or ""),
        email=str(email or ""),
        address=str(address or ""),
        sku=str(sku or ""),
        qty=qty,
        period_start=str(period_start or ""),
        period_end=str(period_end or ""),
        invoice_id=final_invoice_id,
    )

    if ok:
        return {
            "status": "created",
            "invoice_id": final_invoice_id,
            "subscriber_name": str(subscriber_name or ""),
            "sku": str(sku or ""),
            "qty": qty,
        }
    else:
        return {"status": "error", "error": "Failed to append obligation"}
