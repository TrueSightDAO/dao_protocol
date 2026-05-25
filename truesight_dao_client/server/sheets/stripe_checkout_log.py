"""Port of Rails `Gdrive::StripeCheckoutLog` — the **Stripe Social Media Checkout ID** audit tab
(every Stripe checkout lands here; feeds `stripe_sales_sync.gs` ledger routing). Uses the
agroverse_qr_code key. Appends cols A–I, then writes the fee (col L) + environment (col Q)
out-of-band so it never disturbs cols J–P (owned by downstream GAS writers). Dedup on col C."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
SHEET = "Stripe Social Media Checkout ID"
SESSION_COL = 3        # col C (1-based) — Stripe Session ID
STRIPE_FEE_COL = "L"   # col 12, dollars
ENVIRONMENT_COL = "Q"  # col 17, PRODUCTION/SANDBOX


def _key() -> str:
    return get_settings().google_sa_json_qr_sales


def record_exists(session_id: str) -> bool:
    if not (session_id or "").strip():
        return False
    rows = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:I", key_path=_key())
    target = session_id.strip()
    return any(base.cell(r, SESSION_COL).strip() == target for r in (rows[1:] if rows else []))


def append_record(customer_name: str, session_id: str, items: str, total_quantity, amount,
                  currency: str, environment: str | None = None, stripe_fee_cents=None) -> bool:
    key = _key()
    prefix = base.quoted_prefix(SHEET)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = [ts, str(customer_name or ""), str(session_id or ""), "", "",
           str(items or ""), str(total_quantity), str(amount), str(currency or "").upper()]
    try:
        resp = base.append_row(SPREADSHEET_ID, f"{prefix}!A:I", row, key_path=key)
        updated = (resp.get("updates") or {}).get("updatedRange", "")
        m = re.search(r"![A-Z]+(\d+):", updated)
        if m:
            n = m.group(1)
            if stripe_fee_cents is not None:
                base.update_cell(SPREADSHEET_ID, f"{prefix}!{STRIPE_FEE_COL}{n}",
                                 round(float(stripe_fee_cents) / 100.0, 2), key_path=key)
            if environment:
                base.update_cell(SPREADSHEET_ID, f"{prefix}!{ENVIRONMENT_COL}{n}",
                                 str(environment).upper(), key_path=key)
        return True
    except Exception:
        return False
