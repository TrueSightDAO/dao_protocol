"""Port of Rails `Gdrive::TelegramRawLog.add_record` — append a signed submission to the
**Telegram Chat Logs** tab (the DAO ledger intake).

Append-only. Returns the generated ``message_id`` (col D) on success and raises
:class:`AppendFailure` when the append could not be **confirmed**.

Why it raises (2026-09-18): the original swallowed every exception and returned ``""``
with *no logging at all*, so a transient Sheets failure produced a silent, user-invisible
drop while the HTTP caller still got ``200 {"status":"ok"}``. A lost intake row is
indistinguishable from "nothing was submitted" — see OPEN_FOLLOWUPS.md "silent intake drop".
The read-back guard (:func:`_row_present`) keeps the loud path retry-safe: if the Sheets
write actually committed before the error (a read timeout after the row landed), we report
**success**, never failure — otherwise a client retry would double-log the event.

Row layout (A:T, matches the Rails model + Sentinel extension):
  A update_id  B chatroom_id  C chatroom_name  D message_id  E "Edgar"  F ""  G contribution_made
  H "Unknown"  I ""  J "Pending"  K ""  L date(YYYYMMDD)  M "" N "" O ""  P signature_verification
  Q status_info  R api_response  S governor_authority  T is_sentinel
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from . import base

logger = logging.getLogger("dao_protocol.telegram_raw_log")

SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SHEET = "Telegram Chat Logs"

_seq_lock = threading.Lock()
_seq = 0


class AppendFailure(RuntimeError):
    """The intake row could not be appended **and** could not be confirmed on read-back.

    Callers MUST surface this to the submitter (non-2xx) instead of returning success.
    Safe to retry: the row is verified absent, so a retry cannot duplicate it.
    """


def _unique_id() -> str:
    global _seq
    with _seq_lock:
        _seq += 1
        n = _seq
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"Edgar_{ts}_{n:03d}"


def _row_present(message_id: str) -> bool:
    """Read-back guard: True if column D already holds ``message_id``.

    Distinguishes *"append never committed"* (safe to retry, duplicate-free) from
    *"append committed but the confirmation was lost"* (must NOT be reported as failure —
    a client retry would then double-log the event)."""
    if not message_id:
        return False
    try:
        rows = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!D2:D")
    except Exception:
        logger.exception("telegram_raw_log: read-back failed for %s", message_id)
        return False
    return any(r and str(r[0]).strip() == message_id for r in rows)


def add_record(
    contribution_made: str,
    chatroom_id: str = "-1002190388985",
    chatroom_name: str = "Edgar Direct",
    signature_verification: str | None = None,
    governor_authority: str = "",
    is_sentinel: str = "",
) -> str:
    """Append a row; returns the generated message_id (col D) so callers can
    reference it (e.g. ledger emit). Raises :class:`AppendFailure` on an
    unconfirmed append (never a silent ``""``)."""
    message_id = _unique_id()
    row = [
        _unique_id(),  # A update_id
        chatroom_id,  # B
        chatroom_name,  # C
        message_id,  # D message_id
        "Edgar",  # E
        "",  # F
        contribution_made,  # G
        "Unknown",  # H
        "",  # I
        "Pending",  # J
        "",  # K
        datetime.now(timezone.utc).strftime("%Y%m%d"),  # L
        "",
        "",
        "",  # M N O
        signature_verification,  # P
        None,  # Q status_info
        None,  # R api_response
        str(governor_authority or ""),  # S
        str(is_sentinel or ""),  # T
    ]
    try:
        base.append_row(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:T", row)
        return message_id
    except Exception as exc:
        logger.error(
            "telegram_raw_log: intake append FAILED for %s (event starts %r): %s",
            message_id,
            (contribution_made or "")[:60],
            exc,
            exc_info=True,
        )
        if _row_present(message_id):
            logger.warning(
                "telegram_raw_log: %s IS present despite the append error — "
                "lost confirmation, not a drop; reporting success",
                message_id,
            )
            return message_id
        raise AppendFailure(
            f"intake append unconfirmed for {message_id}: {exc}"
        ) from exc
