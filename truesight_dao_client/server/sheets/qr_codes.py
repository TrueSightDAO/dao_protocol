"""Read-only adapter for the **Agroverse QR codes** tab (Main Ledger).

Returns QR code records filtered by manager, owner, SKU (Currency), and status.
Uses the QR-lookup service-account key (same as `qr_code_lookup.py`).
"""

from __future__ import annotations

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
SHEET = "Agroverse QR codes"

# Column indices (1-based) per SCHEMA.md
# A=1: QR Code, B=2: Status, C=3: Price, D=4: Product Image,
# E=5: landing_page, F=6: farm name, G=7: state, H=8: country,
# I=9: Currency (SKU), J=10: Year, K=11: Product Name, L=12: Product Description,
# M=13: Onboarding Email Sent Date, N=14: Tree Planting Date,
# O=15: Tree ID, P=16: Notarization URL, Q=17: Notarization Date,
# R=18: Notarized By, S=19: Owner, T=20: Batch ID,
# U=21: Manager Name (header has line break), V=22: Ledger Name

COL_QR_CODE = 1       # A
COL_STATUS = 2        # B
COL_SKU = 9           # I = Currency
COL_OWNER = 19        # S
COL_MANAGER = 21      # U = Manager Name (header has \n)
COL_LEDGER_NAME = 22  # V
COL_PRICE = 3         # C
COL_FARM = 6          # F
COL_YEAR = 10         # J


def _key() -> str:
    return get_settings().google_sa_json_qr_lookup


def query(
    manager: str | None = None,
    owner: str | None = None,
    sku: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return QR code records matching the given filters.

    All string filters are case-insensitive substring matches, except `status`
    which is an exact match (case-insensitive).
    """
    try:
        rows = base.get_values(
            SPREADSHEET_ID,
            f"{base.quoted_prefix(SHEET)}!A:V",
            key_path=_key(),
        )
    except Exception as exc:
        return [{"error": f"Failed to read sheet: {exc}"}]

    # Skip header row (row 0)
    data_rows = rows[1:] if rows else []
    results: list[dict] = []

    manager_lower = manager.lower().strip() if manager else None
    owner_lower = owner.lower().strip() if owner else None
    sku_lower = sku.lower().strip() if sku else None
    status_lower = status.lower().strip() if status else None

    for row in data_rows:
        if not row:
            continue

        row_qr = base.cell(row, COL_QR_CODE)
        if not row_qr:
            continue

        row_manager = base.cell(row, COL_MANAGER)
        row_owner = base.cell(row, COL_OWNER)
        row_sku = base.cell(row, COL_SKU)
        row_status = base.cell(row, COL_STATUS)

        # Manager filter (substring, case-insensitive)
        if manager_lower and manager_lower not in row_manager.lower():
            continue

        # Owner filter (substring, case-insensitive)
        if owner_lower and owner_lower not in row_owner.lower():
            continue

        # SKU filter (substring, case-insensitive)
        if sku_lower and sku_lower not in row_sku.lower():
            continue

        # Status filter (exact match, case-insensitive)
        if status_lower and row_status.lower().strip() != status_lower:
            continue

        results.append({
            "qr_code": row_qr,
            "sku": row_sku,
            "status": row_status,
            "manager": row_manager,
            "owner": row_owner,
            "price": base.cell(row, COL_PRICE),
            "farm": base.cell(row, COL_FARM),
            "year": base.cell(row, COL_YEAR),
            "ledger_name": base.cell(row, COL_LEDGER_NAME),
            "source_sheet": SHEET,
            "source_row": len(results) + 2,
        })

        if len(results) >= limit:
            break

    return results
