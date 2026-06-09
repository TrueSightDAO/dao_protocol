"""Subscription Fulfillment Queue — the PENDING/FULFILLED obligation tracker.

Schema (columns A–L):
  A: subscriber_name
  B: email
  C: address
  D: sku
  E: qty
  F: period_start (YYYY-MM-DD)
  G: period_end (YYYY-MM-DD)
  H: invoice_id (unique — dedup key)
  I: status (PENDING / FULFILLED / FAILED)
  J: fulfilled_by
  K: tracking_number
  L: fulfilled_at (ISO timestamp)

Uses the agroverse_qr_code_manager SA key (same as stripe_checkout_log).
Auto-creates the tab on first access if it doesn't exist.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
SHEET = "Subscription Fulfillment Queue"

HEADERS = [
    "subscriber_name", "email", "address", "sku", "qty",
    "period_start", "period_end", "invoice_id", "status",
    "fulfilled_by", "tracking_number", "fulfilled_at"
]

INVOICE_COL = 8  # col H (1-based)
STATUS_COL = 9   # col I


def _key() -> str:
    return get_settings().google_sa_json_qr_sales


def _ensure_tab() -> None:
    """Create the tab if it doesn't exist. Best-effort; callers handle exceptions."""
    key = _key()
    try:
        # Probe the sheet — if it exists, this returns data; if not, Sheets API returns 400
        rows = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A1:A1", key_path=key)
        if rows:
            return  # Tab exists
    except Exception:
        pass

    # Tab doesn't exist — create it
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        key, scopes=("https://www.googleapis.com/auth/spreadsheets",)
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Add the sheet tab
    body = {"requests": [{"addSheet": {"properties": {"title": SHEET}}}]}
    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()

    # Write header row
    base.append_row(
        SPREADSHEET_ID,
        f"{base.quoted_prefix(SHEET)}!A:L",
        HEADERS,
        key_path=key,
    )


def append_obligation(
    subscriber_name: str,
    email: str,
    address: str,
    sku: str,
    qty: int,
    period_start: str,
    period_end: str,
    invoice_id: str,
) -> bool:
    """Append a PENDING obligation. Idempotent on invoice_id."""
    _ensure_tab()
    if record_exists(invoice_id):
        return True  # Already exists — idempotent

    key = _key()
    prefix = base.quoted_prefix(SHEET)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = [
        str(subscriber_name or ""),
        str(email or ""),
        str(address or ""),
        str(sku or ""),
        str(qty or 1),
        str(period_start or ""),
        str(period_end or ""),
        str(invoice_id or ""),
        "PENDING",
        "",  # fulfilled_by
        "",  # tracking_number
        "",  # fulfilled_at
    ]
    try:
        base.append_row(SPREADSHEET_ID, f"{prefix}!A:L", row, key_path=key)
        return True
    except Exception:
        return False


def mark_fulfilled(
    invoice_id: str,
    fulfilled_by: str,
    tracking_number: str,
) -> bool:
    """Mark a PENDING obligation as FULFILLED. Finds by invoice_id."""
    _ensure_tab()
    row_num = _find_row_by_invoice_id(invoice_id)
    if row_num is None:
        return False

    key = _key()
    prefix = base.quoted_prefix(SHEET)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Update status (col I), fulfilled_by (col J), tracking_number (col K), fulfilled_at (col L)
        base.batch_update(
            SPREADSHEET_ID,
            [
                {"range": f"{prefix}!I{row_num}", "values": [["FULFILLED"]]},
                {"range": f"{prefix}!J{row_num}", "values": [[str(fulfilled_by or "")]]},
                {"range": f"{prefix}!K{row_num}", "values": [[str(tracking_number or "")]]},
                {"range": f"{prefix}!L{row_num}", "values": [[ts]]},
            ],
            key_path=key,
        )
        return True
    except Exception:
        return False


def list_pending() -> list[dict]:
    """Return all PENDING obligations as dicts."""
    _ensure_tab()
    key = _key()
    prefix = base.quoted_prefix(SHEET)
    try:
        rows = base.get_values(SPREADSHEET_ID, f"{prefix}!A:L", key_path=key)
    except Exception:
        return []

    if not rows or len(rows) < 2:
        return []

    results = []
    for row in rows[1:]:  # Skip header
        if len(row) < 9:
            continue
        status = base.cell(row, STATUS_COL).strip().upper()
        if status != "PENDING":
            continue
        results.append({
            "subscriber_name": base.cell(row, 1),
            "email": base.cell(row, 2),
            "address": base.cell(row, 3),
            "sku": base.cell(row, 4),
            "qty": base.to_int(base.cell(row, 5)),
            "period_start": base.cell(row, 6),
            "period_end": base.cell(row, 7),
            "invoice_id": base.cell(row, 8),
            "status": status,
            "fulfilled_by": base.cell(row, 10),
            "tracking_number": base.cell(row, 11),
            "fulfilled_at": base.cell(row, 12),
        })
    return results


def record_exists(invoice_id: str) -> bool:
    """Check if an invoice_id already exists in the queue."""
    return _find_row_by_invoice_id(invoice_id) is not None


def _find_row_by_invoice_id(invoice_id: str) -> int | None:
    """1-based row number for the given invoice_id, or None."""
    if not (invoice_id or "").strip():
        return None
    target = invoice_id.strip()
    _ensure_tab()
    key = _key()
    prefix = base.quoted_prefix(SHEET)
    try:
        rows = base.get_values(SPREADSHEET_ID, f"{prefix}!H:H", key_path=key)
    except Exception:
        return None
    for i, row in enumerate(rows):
        if row and str(row[0]).strip() == target:
            return i + 1  # 1-based (row 1 = header)
    return None
