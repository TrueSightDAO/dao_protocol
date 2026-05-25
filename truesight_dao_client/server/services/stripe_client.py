"""Thin Stripe wrapper for the QR-code / meta-checkout flows (PR6). Lazy `stripe` import; key from
settings (`DAO_PROTOCOL_STRIPE_SECRET_KEY`). Returns None when no key is set (gate-off safe)."""

from __future__ import annotations

from ..config import get_settings


def _stripe():
    key = get_settings().stripe_secret_key
    if not key:
        return None
    import stripe

    stripe.api_key = key
    return stripe


def create_qr_checkout_session(qr_code: str, product_data: dict, unit_amount_cents: int,
                               success_url: str, cancel_url: str):
    """Create a `mode=payment` Checkout Session for a MINTED QR. Returns the session (with `.url`)
    or None if Stripe isn't configured."""
    s = _stripe()
    if s is None:
        return None
    return s.checkout.Session.create(
        payment_method_types=["card"],
        customer_creation="always",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": product_data,
                "unit_amount": unit_amount_cents,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"qr_code": qr_code, "product": product_data.get("name", "Product")},
    )


def retrieve_session_with_charges(session_id: str):
    s = _stripe()
    if s is None:
        return None
    return s.checkout.Session.retrieve(
        session_id, expand=["payment_intent", "payment_intent.charges"]
    )


def retrieve_balance_transaction(bt_id: str):
    s = _stripe()
    if s is None:
        return None
    return s.BalanceTransaction.retrieve(bt_id)
