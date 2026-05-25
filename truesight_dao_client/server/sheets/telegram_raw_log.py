"""Port of Rails `Gdrive::TelegramRawLog.add_record` — append a signed submission to the
**Telegram Chat Logs** tab (the DAO ledger intake). Append-only; never raises (returns bool).

Row layout (A:S, matches the Rails model):
  A update_id  B chatroom_id  C chatroom_name  D message_id  E "Edgar"  F ""  G contribution_made
  H "Unknown"  I ""  J "Pending"  K ""  L date(YYYYMMDD)  M "" N "" O ""  P signature_verification
  Q status_info  R api_response  S governor_authority
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import base

SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SHEET = "Telegram Chat Logs"

_seq_lock = threading.Lock()
_seq = 0


def _unique_id() -> str:
    global _seq
    with _seq_lock:
        _seq += 1
        n = _seq
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"Edgar_{ts}_{n:03d}"


def add_record(contribution_made: str, chatroom_id: str = "-1002190388985",
               chatroom_name: str = "Edgar Direct", signature_verification: str | None = None,
               governor_authority: str = "") -> bool:
    try:
        row = [
            _unique_id(),            # A update_id
            chatroom_id,             # B
            chatroom_name,           # C
            _unique_id(),            # D message_id
            "Edgar",                 # E
            "",                      # F
            contribution_made,       # G
            "Unknown",               # H
            "",                      # I
            "Pending",               # J
            "",                      # K
            datetime.now(timezone.utc).strftime("%Y%m%d"),  # L
            "", "", "",              # M N O
            signature_verification,  # P
            None,                    # Q status_info
            None,                    # R api_response
            str(governor_authority or ""),  # S
        ]
        base.append_row(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:S", row)
        return True
    except Exception:
        return False
