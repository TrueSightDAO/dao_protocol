"""Design Events Log — dedicated tab for white-label design event dedup + audit.

Spreadsheet: same workbook as Telegram Chat Logs (1qbZZhf-...)
Tab: "Design Events" (columns A–J)
  A update_id  B event_type  C email  D design_id  E order_id  F filename
  G status  H created_at  I signature_verification  J raw_text

Row-level dedup:
  - DESIGN UPLOAD EVENT: unique on (design_id, email) — if design already logged, reject
  - DESIGN ORDER EVENT: unique on (order_id, email) — if order already logged, reject
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import base

SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SHEET = "Design Events"

COL_UPDATE_ID, COL_EVENT_TYPE, COL_EMAIL, COL_DESIGN_ID = 1, 2, 3, 4
COL_ORDER_ID, COL_FILENAME, COL_STATUS, COL_CREATED_AT = 5, 6, 7, 8
COL_SIG_VERIFY, COL_RAW_TEXT = 9, 10

_seq_lock = threading.Lock()
_seq = 0


def _unique_id() -> str:
    global _seq
    with _seq_lock:
        _seq += 1
        n = _seq
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"DE_{ts}_{n:03d}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _key() -> str:
    from ..config import get_settings
    return get_settings().google_sa_json


def _find_existing(event_type: str, email: str, design_id: str = "", order_id: str = "") -> bool:
    """Check if a matching event already exists in the Design Events tab.

    For uploads: match on event_type + email + design_id
    For orders: match on event_type + email + order_id
    """
    try:
        prefix = base.quoted_prefix(SHEET)
        rows = base.get_values(SPREADSHEET_ID, f"{prefix}!A2:J", key_path=_key())
        if not rows:
            return False
        email_norm = (email or "").lower().strip()
        for row in rows:
            if not row:
                continue
            r_event = base.cell(row, COL_EVENT_TYPE).strip()
            r_email = base.cell(row, COL_EMAIL).strip().lower()
            if r_event != event_type or r_email != email_norm:
                continue
            if event_type == "DESIGN UPLOAD EVENT":
                r_design = base.cell(row, COL_DESIGN_ID).strip()
                if r_design == (design_id or "").strip():
                    return True
            elif event_type == "DESIGN ORDER EVENT":
                r_order = base.cell(row, COL_ORDER_ID).strip()
                if r_order == (order_id or "").strip():
                    return True
        return False
    except Exception:
        return False


def log_upload(email: str, design_id: str, filename: str, raw_text: str,
               signature_verification: str = "success") -> bool:
    """Log a DESIGN UPLOAD EVENT. Returns False if already logged (dedup hit)."""
    if _find_existing("DESIGN UPLOAD EVENT", email, design_id=design_id):
        return False
    try:
        row = [
            _unique_id(),              # A
            "DESIGN UPLOAD EVENT",     # B
            (email or "").lower().strip(),  # C
            (design_id or "").strip(), # D
            "",                        # E (order_id)
            (filename or "").strip(),  # F
            "Pending",                 # G
            _now(),                    # H
            signature_verification,    # I
            (raw_text or "")[:500],    # J (truncated)
        ]
        base.append_row(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:J", row, key_path=_key())
        return True
    except Exception:
        return False


def log_order(email: str, design_id: str, order_id: str, quantity: str, raw_text: str,
              signature_verification: str = "success") -> bool:
    if _find_existing("DESIGN ORDER EVENT", email, order_id=order_id):
        return False
    try:
        row = [
            _unique_id(),              # A
            "DESIGN ORDER EVENT",      # B
            (email or "").lower().strip(),  # C
            (design_id or "").strip(), # D
            (order_id or "").strip(),  # E
            f"qty={quantity}",         # F
            "Pending",                 # G
            _now(),                    # H
            signature_verification,    # I
            (raw_text or "")[:500],    # J
        ]
        base.append_row(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:J", row, key_path=_key())
        return True
    except Exception:
        return False
