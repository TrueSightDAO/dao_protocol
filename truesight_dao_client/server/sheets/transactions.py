"""Read-only adapter for the **QR Code Sales** tab (Telegram & Submissions workbook).

Returns sale records filtered by partner name (substring), SKU, and date range.
Uses the QR-sales service-account key (same as `qr_code_sales.py`).
"""

from __future__ import annotations

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SHEET = "QR Code Sales"

# Column indices (1-based) per SCHEMA.md
# A=1: Telegram Update ID, B=2: Chatroom ID, C=3: Chatroom Name,
# D=4: Message ID / Reporter, E=5: Contributor Name, F=6: Contribution Made,
# G=7: Status date (YYYYMMDD), H=8: Currency (SKU), I=9: Amount (qty),
# J=10: Status, K=11: QR Code, L=12: Owner email,
# M=13: Stripe Session ID, N=14: Shipping Provider, O=15: Tracking Number,
# P=16: Sold by, Q=17: Cash Collected By, R=18: Remarks

COL_PARTNER = 5       # E = Contributor Name (person reporting / partner name)
COL_DATE = 7          # G = Status date
COL_SKU = 8           # H = Currency (product/SKU name)
COL_QTY = 9           # I = Amount
COL_QR_CODE = 11      # K = QR Code
COL_STATUS = 10       # J = Status
COL_VALUE = 9         # I = Amount (also used as value proxy)


def _key() -> str:
    return get_settings().google_sa_json_qr_sales


def query(
    partner: str | None = None,
    sku: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return sale records matching the given filters.

    All string filters are case-insensitive substring matches.
    """
    try:
        rows = base.get_values(
            SPREADSHEET_ID,
            f"{base.quoted_prefix(SHEET)}!A:R",
            key_path=_key(),
        )
    except Exception as exc:
        return [{"error": f"Failed to read sheet: {exc}"}]

    # Skip header row (row 0)
    data_rows = rows[1:] if rows else []
    results: list[dict] = []

    partner_lower = partner.lower().strip() if partner else None
    sku_lower = sku.lower().strip() if sku else None

    for row in data_rows:
        if len(row) < 9:
            continue

        row_partner = base.cell(row, COL_PARTNER)
        row_date = base.cell(row, COL_DATE)
        row_sku = base.cell(row, COL_SKU)

        # Partner filter (substring, case-insensitive)
        if partner_lower and partner_lower not in row_partner.lower():
            continue

        # SKU filter (substring, case-insensitive)
        if sku_lower and sku_lower not in row_sku.lower():
            continue

        # Date range filter
        if from_date and row_date < from_date:
            continue
        if to_date and row_date > to_date:
            continue

        results.append({
            "date": row_date,
            "partner": row_partner,
            "sku": row_sku,
            "qty": base.to_int(base.cell(row, COL_QTY)),
            "qr_code": base.cell(row, COL_QR_CODE),
            "value": base.to_int(base.cell(row, COL_VALUE)),
            "status": base.cell(row, COL_STATUS),
            "source_sheet": SHEET,
            "source_row": len(results) + 2,  # approximate (header + index)
        })

        if len(results) >= limit:
            break

    return results
