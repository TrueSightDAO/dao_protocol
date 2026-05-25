"""Port of Rails `Gdrive::EmailAgentDrafts` — open/click counters for the Hit List
"Email Agent Drafts" tab. `tid` = suggestion_id (col A). Open → bump col N, click →
bump col O. Recipient (col E) must match when provided. Never raises."""

from __future__ import annotations

import threading

from . import base

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
SHEET = "Email Agent Drafts"
LAST_COL = "O"

COL_TO_EMAIL = 5       # E
COL_OPEN = 14          # N
COL_CLICK_THROUGH = 15  # O

_lock = threading.Lock()


def _read_row(row: int) -> list:
    vals = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A{row}:{LAST_COL}{row}")
    return vals[0] if vals else []


def _recipient_ok(current: list, recipient_email) -> bool:
    if recipient_email is None:
        return True
    return base.cell(current, COL_TO_EMAIL).strip().lower() == str(recipient_email).strip().lower()


def _bump(suggestion_id: str, col_letter: str, col_idx: int, recipient_email) -> bool:
    if not (suggestion_id or "").strip():
        return False
    try:
        with _lock:
            row = base.find_row_by_col_a(SPREADSHEET_ID, SHEET, suggestion_id)
            if not row:
                return False
            current = _read_row(row)
            if not _recipient_ok(current, recipient_email):
                return False
            count = base.to_int(base.cell(current, col_idx)) + 1
            base.batch_update(SPREADSHEET_ID, [{
                "range": f"{base.quoted_prefix(SHEET)}!{col_letter}{row}:{col_letter}{row}",
                "values": [[str(count)]],
            }])
            return True
    except Exception:
        return False


def record_open(suggestion_id: str, recipient_email=None) -> bool:
    return _bump(suggestion_id, "N", COL_OPEN, recipient_email)


def record_click(suggestion_id: str, recipient_email=None) -> bool:
    return _bump(suggestion_id, "O", COL_CLICK_THROUGH, recipient_email)
