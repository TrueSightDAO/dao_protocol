"""Service-account Google Sheets v4 client + small read/update helpers.

Mirrors the Rails `Gdrive` session pattern (`GoogleDrive::Session.from_service_account_key`)
and the demo's `service_account.Credentials` approach. The service-account JSON path comes
from settings (`DAO_PROTOCOL_GOOGLE_SA_JSON`); on `seni_ror_new` it defaults to the same key
Edgar's Rails app already uses, so no new credential needs provisioning.

All callers treat sheet access as best-effort — the tracking routes never let a Sheets error
break their redirect (see routes/tracking.py).
"""

from __future__ import annotations

import functools
import threading

from ..config import get_settings

_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def sheets_service():
    """Cached Sheets v4 service. Imports google libs lazily so the server (and
    health/proxy routes) don't hard-depend on them being installed/credentialed."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        get_settings().google_sa_json, scopes=_SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def quoted_prefix(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def get_values(spreadsheet_id: str, a1_range: str) -> list[list]:
    resp = (
        sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=a1_range)
        .execute()
    )
    return resp.get("values", [])


def batch_update(spreadsheet_id: str, data: list[dict]) -> dict:
    """`data` = [{"range": "...", "values": [[...]]}, …]. USER_ENTERED, like the Rails port."""
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    return (
        sheets_service()
        .spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
        .execute()
    )


def append_row(spreadsheet_id: str, a1_range: str, row_values: list) -> dict:
    """Append one row (Sheets `values.append`, USER_ENTERED, INSERT_ROWS) — like the Rails
    `TelegramRawLog.add_record` append (fast, doesn't reload the grid)."""
    return (
        sheets_service()
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=a1_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row_values]},
        )
        .execute()
    )


def find_row_by_col_a(spreadsheet_id: str, sheet_name: str, value: str) -> int | None:
    """1-based row whose column A equals `value` (header is row 1), or None."""
    value = (value or "").strip()
    if not value:
        return None
    rows = get_values(spreadsheet_id, f"{quoted_prefix(sheet_name)}!A2:A")
    for i, row in enumerate(rows):
        if row and str(row[0]).strip() == value:
            return i + 2
    return None


def cell(row: list, one_based_idx: int) -> str:
    """Column value (1-based) from a row list, '' if short (Sheets omits trailing blanks)."""
    return str(row[one_based_idx - 1]) if len(row) >= one_based_idx else ""


def to_int(s) -> int:
    try:
        return int(str(s).strip() or 0)
    except (TypeError, ValueError):
        return 0
