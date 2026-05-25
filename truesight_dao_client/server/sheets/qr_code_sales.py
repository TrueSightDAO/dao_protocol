"""Port of the sheet side of `qr_code_check_controller#index` `session_id` reconcile (uses the
QR-sales service-account key): dedup against **QR Code Sales** (col E), mark the **Agroverse QR
codes** row `SOLD` + buyer email, and append the sale row (A–R)."""

from __future__ import annotations

from ..config import get_settings
from . import base

AGROVERSE_QR_SS = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
AGROVERSE_QR_SHEET = "Agroverse QR codes"
SALES_SS = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
SALES_SHEET = "QR Code Sales"


def _key() -> str:
    return get_settings().google_sa_json_qr_sales


def _col_letter(idx_1based: int) -> str:
    s, n = "", idx_1based
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def already_recorded(qr_code: str) -> bool:
    """True if this qr_code already has a QR Code Sales row (col E, index 4)."""
    rows = base.get_values(SALES_SS, f"{base.quoted_prefix(SALES_SHEET)}!A:R", key_path=_key())
    target = (qr_code or "").strip()
    return any(len(r) > 4 and str(r[4]).strip() == target for r in rows)


def mark_sold_and_record(qr_code: str, buyer_email: str, net_amount, fee_amount, total_amount,
                         currency: str, session_id: str, sales_date: str) -> dict:
    """Flip the Agroverse QR row to SOLD (+ buyer email) and append the QR Code Sales row.
    Returns {"ok": bool, "error"?: str}. Caller dedups via already_recorded() first."""
    key = _key()
    qr_prefix = base.quoted_prefix(AGROVERSE_QR_SHEET)
    try:
        header = base.get_values(AGROVERSE_QR_SS, f"{qr_prefix}!1:1", key_path=key)
        headers = header[0] if header else []
        status_idx = next((i + 1 for i, h in enumerate(headers) if str(h).strip().lower() == "status"), None)
        if not status_idx:
            return {"ok": False, "error": "status column not found"}

        row_num = base.find_row_by_col_a(AGROVERSE_QR_SS, AGROVERSE_QR_SHEET, qr_code, key_path=key)
        if not row_num:
            return {"ok": False, "error": f"QR code {qr_code} not found in Agroverse QR codes"}

        rv_rows = base.get_values(AGROVERSE_QR_SS, f"{qr_prefix}!{row_num}:{row_num}", key_path=key)
        rv = rv_rows[0] if rv_rows else []
        manager_name = base.cell(rv, 21).strip() or "Stripe Checkout"   # col U
        ledger_url = base.cell(rv, 3).strip()                            # col C

        base.update_cell(AGROVERSE_QR_SS, f"{qr_prefix}!{_col_letter(status_idx)}{row_num}", "SOLD", key_path=key)
        if buyer_email:
            base.update_cell(AGROVERSE_QR_SS, f"{qr_prefix}!L{row_num}", buyer_email, key_path=key)  # col L

        msg = (f"Stripe Checkout: QR code {qr_code} sold for ${total_amount} "
               f"(net ${net_amount} after ${fee_amount} Stripe fee)")
        sale_row = [
            f"stripe_{session_id}", f"stripe_{session_id}", msg, manager_name, qr_code,
            net_amount, ledger_url, sales_date, currency or "Unknown", "", "",
            buyer_email or "", str(session_id), "", "", manager_name, manager_name,
            "Stripe checkout (online)",
        ]
        base.append_row(SALES_SS, f"{base.quoted_prefix(SALES_SHEET)}!A:R", sale_row, key_path=key)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
