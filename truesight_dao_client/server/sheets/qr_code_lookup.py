"""Port of Rails `Gdrive::QrCodeLookup.lookup` — look up a QR code row on the **Agroverse QR codes**
tab (Main Ledger) and return a header→value record (or `{"error": …}`). Uses the QR-lookup
service-account key. Dup header labels (e.g. "Product Image") keep the first non-blank value."""

from __future__ import annotations

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
SHEET = "Agroverse QR codes"
DATA_START_ROW = 2


def lookup(qr_code: str) -> dict:
    qr_code = (qr_code or "").strip()
    if not qr_code:
        return {"error": "Missing qr_code", "qr_code": qr_code}
    key = get_settings().google_sa_json_qr_lookup
    prefix = base.quoted_prefix(SHEET)
    try:
        col = base.get_values(SPREADSHEET_ID, f"{prefix}!A:A", key_path=key)
        match_row = None
        for idx, row in enumerate(col):
            if row and str(row[0]).strip() == qr_code:
                match_row = idx + 1  # 1-based
                break
        if not match_row:
            return {"error": f"QR code {qr_code} not found", "qr_code": qr_code}
        if match_row < DATA_START_ROW:
            return {"error": f"Invalid data row {match_row}", "qr_code": qr_code}

        ranges = base.batch_get(
            SPREADSHEET_ID, [f"{prefix}!1:1", f"{prefix}!{match_row}:{match_row}"], key_path=key
        )
        headers = ranges[0][0] if ranges and ranges[0] else []
        data_row = ranges[1][0] if len(ranges) > 1 and ranges[1] else []

        record: dict = {"qr_code": qr_code}
        for i, raw_header in enumerate(headers):
            header = str(raw_header).strip()
            if not header:
                continue
            value = data_row[i] if i < len(data_row) else None
            if header in record:
                if not record[header] and value:
                    record[header] = value
            else:
                record[header] = value
        return record
    except Exception as exc:  # never 500 a public scan
        return {"error": str(exc), "qr_code": qr_code}
