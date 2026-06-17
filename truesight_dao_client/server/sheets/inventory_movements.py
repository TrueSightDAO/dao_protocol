"""Read-only adapter for the **Inventory Movement** tab (Telegram & Submissions workbook).

Returns inventory transfer records filtered by person (sender or recipient),
date range, and role. Uses the default service-account key (edgar_dapp_listener).
"""

from __future__ import annotations

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SHEET = "Inventory Movement"

# Column indices (1-based) per SCHEMA.md
# A=1: Telegram Update ID, B=2: Chatroom ID, C=3: Chatroom Name,
# D=4: Telegram Message ID, E=5: Contributor Name, F=6: Contribution Made,
# G=7: Status Date (YYYYMMDD), H=8: SENDER NAME, I=9: RECIPIENT NAME,
# J=10: CURRENCY (SKU), K=11: AMOUNT (qty), L=12: LEDGER_NAME,
# M=13: LEDGER_URL, N=14: STATUS, O=15: RECORD ROWS

COL_DATE = 7           # G = Status Date
COL_SENDER = 8         # H = SENDER NAME
COL_RECIPIENT = 9      # I = RECIPIENT NAME
COL_SKU = 10           # J = CURRENCY
COL_QTY = 11           # K = AMOUNT
COL_LEDGER_NAME = 12   # L = LEDGER_NAME
COL_STATUS = 14        # N = STATUS


def _key() -> str:
    return get_settings().google_sa_json


def query(
    person: str | None = None,
    role: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return inventory movement records matching the given filters.

    `person` is a case-insensitive substring match against both SENDER NAME
    and RECIPIENT NAME (or just one if `role` is specified).
    `role` can be "sender" or "recipient" to narrow the match.
    """
    try:
        rows = base.get_values(
            SPREADSHEET_ID,
            f"{base.quoted_prefix(SHEET)}!A:O",
            key_path=_key(),
        )
    except Exception as exc:
        return [{"error": f"Failed to read sheet: {exc}"}]

    # Skip header row (row 0)
    data_rows = rows[1:] if rows else []
    results: list[dict] = []

    person_lower = person.lower().strip() if person else None
    role_lower = role.lower().strip() if role else None

    for row in data_rows:
        if len(row) < 11:
            continue

        row_sender = base.cell(row, COL_SENDER)
        row_recipient = base.cell(row, COL_RECIPIENT)
        row_date = base.cell(row, COL_DATE)

        # Person filter
        if person_lower:
            if role_lower == "sender":
                if person_lower not in row_sender.lower():
                    continue
            elif role_lower == "recipient":
                if person_lower not in row_recipient.lower():
                    continue
            else:
                # Match against either sender or recipient
                if person_lower not in row_sender.lower() and person_lower not in row_recipient.lower():
                    continue

        # Date range filter
        if from_date and row_date < from_date:
            continue
        if to_date and row_date > to_date:
            continue

        results.append({
            "date": row_date,
            "sender": row_sender,
            "recipient": row_recipient,
            "sku": base.cell(row, COL_SKU),
            "qty": base.to_int(base.cell(row, COL_QTY)),
            "ledger_name": base.cell(row, COL_LEDGER_NAME),
            "status": base.cell(row, COL_STATUS),
            "source_sheet": SHEET,
            "source_row": len(results) + 2,
        })

        if len(results) >= limit:
            break

    return results
