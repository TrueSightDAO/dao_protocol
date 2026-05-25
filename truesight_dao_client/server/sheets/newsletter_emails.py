"""Port of Rails `Gdrive::NewsletterEmails` — open/click tracking for the
"Agroverse News Letter Emails" tab. Best-effort + idempotent: on first open/click
stamps the *_first_* timestamp, always bumps last_* + count; unknown id → no-op.
Recipient (col E) must match when provided, so a stale/spoofed link can't write
another row. Never raises (returns False on any failure)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import base

SPREADSHEET_ID = "1ed3q3SJ8ztGwfWit6Wxz_S72Cn5jKQFkNrHpeOVXP8s"
SHEET = "Agroverse News Letter Emails"
LAST_COL = "P"

COL_RECIPIENT = 5       # E
COL_FIRST_OPENED = 9    # I
COL_OPEN_COUNT = 11     # K
COL_FIRST_CLICKED = 13  # M
COL_CLICK_COUNT = 15    # O

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_row(row: int) -> list:
    vals = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A{row}:{LAST_COL}{row}")
    return vals[0] if vals else []


def _recipient_ok(current: list, recipient_email) -> bool:
    if recipient_email is None:
        return True
    return base.cell(current, COL_RECIPIENT).strip().lower() == str(recipient_email).strip().lower()


def record_open(message_uuid: str, recipient_email=None) -> bool:
    if not (message_uuid or "").strip():
        return False
    try:
        with _lock:
            row = base.find_row_by_col_a(SPREADSHEET_ID, SHEET, message_uuid)
            if not row:
                return False
            current = _read_row(row)
            if not _recipient_ok(current, recipient_email):
                return False
            now = _now()
            first = base.cell(current, COL_FIRST_OPENED).strip() or now
            count = base.to_int(base.cell(current, COL_OPEN_COUNT)) + 1
            base.batch_update(SPREADSHEET_ID, [{
                "range": f"{base.quoted_prefix(SHEET)}!H{row}:K{row}",
                "values": [["TRUE", first, now, str(count)]],
            }])
            return True
    except Exception:
        return False


def record_click(message_uuid: str, recipient_email=None, url=None) -> bool:
    if not (message_uuid or "").strip():
        return False
    try:
        with _lock:
            row = base.find_row_by_col_a(SPREADSHEET_ID, SHEET, message_uuid)
            if not row:
                return False
            current = _read_row(row)
            if not _recipient_ok(current, recipient_email):
                return False
            now = _now()
            first = base.cell(current, COL_FIRST_CLICKED).strip() or now
            count = base.to_int(base.cell(current, COL_CLICK_COUNT)) + 1
            base.batch_update(SPREADSHEET_ID, [{
                "range": f"{base.quoted_prefix(SHEET)}!L{row}:P{row}",
                "values": [["TRUE", first, now, str(count), str(url or "")]],
            }])
            return True
    except Exception:
        return False
