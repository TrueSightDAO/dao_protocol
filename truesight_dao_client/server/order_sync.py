"""Order-sync audit log — port of the non-Wix path of Rails `MetaCheckoutOrderSync#sync!`
(PR6b, scoped). For a Stripe `checkout.session.completed`, append the session to the **Stripe
Social Media Checkout ID** audit tab (which feeds `stripe_sales_sync.gs` ledger routing).

Scope (per operator decision A): only the **ledger-tagged** path is ported. The `channel == meta`
Wix order-creation path is DEPRECATED and stays on Rails (skipped here). Rails' shared
`/stripe_webhook` delegates `checkout.session.completed` session ids to this module.
"""

from __future__ import annotations

import re

from .services import stripe_client
from .sheets import stripe_checkout_log


def _metadata(session) -> dict:
    return getattr(session, "metadata", None) or {}


def _ledger_tagged(metadata: dict) -> bool:
    ledger = str(metadata.get("ledger") or "").strip()
    if ledger and re.fullmatch(r"[A-Z0-9]+", ledger):
        return metadata.get("channel") != "meta"
    return False


def _environment_label(session) -> str:
    livemode = getattr(session, "livemode", None)
    if livemode is True:
        return "PRODUCTION"
    if livemode is False:
        return "SANDBOX"
    return "SANDBOX" if str(getattr(session, "id", "")).startswith("cs_test_") else "PRODUCTION"


def _line_item_summary(session) -> str:
    data = getattr(getattr(session, "line_items", None), "data", None) or []
    if data:
        item = data[0]
        desc = getattr(item, "description", None)
        if not desc:
            price = getattr(item, "price", None)
            product = getattr(price, "product", None) if price else None
            desc = getattr(product, "name", None) if product else None
        if desc:
            return desc
    ledger = _metadata(session).get("ledger")
    return f"[{ledger.upper()}] — Stripe checkout" if ledger else "Stripe checkout"


def _customer_name(session) -> str:
    cd = getattr(session, "customer_details", None) or {}
    return cd.get("name") or cd.get("email") or ""


def _fee_cents(session):
    try:
        charge = session.payment_intent.charges.data[0]
        bt = charge.balance_transaction
        if isinstance(bt, str):
            bt = stripe_client.retrieve_balance_transaction(bt)
        return bt.fee
    except Exception:
        return None


def sync(session_id: str) -> dict:
    """Retrieve the session and, if it's ledger-tagged, append it to the audit log (idempotent)."""
    session = stripe_client.retrieve_session_full(session_id)
    if session is None:
        return {"status": "error", "error": "Stripe not configured"}

    metadata = _metadata(session)
    if metadata.get("channel") == "meta":
        return {"status": "skipped", "reason": "meta/Wix order path stays on Rails (Wix deprecated)"}
    if not _ledger_tagged(metadata):
        return {"status": "skipped", "reason": "not ledger-tagged"}

    if stripe_checkout_log.record_exists(session_id):
        return {"status": "already_exists"}

    ok = stripe_checkout_log.append_record(
        customer_name=_customer_name(session),
        session_id=session_id,
        items=_line_item_summary(session),
        total_quantity=1,
        amount=(getattr(session, "amount_total", 0) or 0) / 100.0,
        currency=getattr(session, "currency", None) or "usd",
        environment=_environment_label(session),
        stripe_fee_cents=_fee_cents(session),
    )
    return {"status": "created"} if ok else {"status": "error", "error": "append failed"}
