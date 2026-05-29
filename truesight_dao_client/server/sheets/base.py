"""Service-account Google Sheets v4 client + small read/update helpers.

Supports **multiple** service-account keys (different Edgar sheets use different keys — e.g. the
QR-code tabs use `cypher_defense_gdrive_key.json` / `agroverse_qr_code_gdrive_key.json` while the
tracking/telegram tabs use `edgar_dapp_listener_key.json`). Pass `key_path=` to pick the key;
default is `google_sa_json`. The key directory is resolved per-host by `config.py`
(`google_creds_dir` / `GOOGLE_CREDS_DIR` → built-in dirs → legacy Edgar box), so the same
filenames work on the Edgar box, the autopilot EC2, or the dao_protocol host. Sheet access is
best-effort at the call sites.
"""

from __future__ import annotations

import functools
import threading

from ..config import get_settings

_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
_lock = threading.Lock()


@functools.lru_cache(maxsize=None)
def _service_for(key_path: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(key_path, scopes=_SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def sheets_service(key_path: str | None = None):
    """Cached Sheets v4 service for `key_path` (default = `google_sa_json`). Lazy google imports."""
    return _service_for(key_path or get_settings().google_sa_json)


def quoted_prefix(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def get_values(spreadsheet_id: str, a1_range: str, key_path: str | None = None) -> list[list]:
    resp = (
        sheets_service(key_path)
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=a1_range)
        .execute()
    )
    return resp.get("values", [])


def batch_get(spreadsheet_id: str, ranges: list[str], key_path: str | None = None) -> list[list[list]]:
    resp = (
        sheets_service(key_path)
        .spreadsheets()
        .values()
        .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges)
        .execute()
    )
    return [vr.get("values", []) for vr in resp.get("valueRanges", [])]


def batch_update(spreadsheet_id: str, data: list[dict], key_path: str | None = None) -> dict:
    """`data` = [{"range": "...", "values": [[...]]}, …]. USER_ENTERED, like the Rails port."""
    body = {"valueInputOption": "USER_ENTERED", "data": data}
    return (
        sheets_service(key_path)
        .spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
        .execute()
    )


def update_cell(spreadsheet_id: str, a1_range: str, value, key_path: str | None = None) -> dict:
    return (
        sheets_service(key_path)
        .spreadsheets()
        .values()
        .update(spreadsheetId=spreadsheet_id, range=a1_range,
                valueInputOption="USER_ENTERED", body={"values": [[value]]})
        .execute()
    )


def append_row(spreadsheet_id: str, a1_range: str, row_values: list, key_path: str | None = None) -> dict:
    """Append one row (Sheets `values.append`, USER_ENTERED, INSERT_ROWS)."""
    return (
        sheets_service(key_path)
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


def find_row_by_col_a(spreadsheet_id: str, sheet_name: str, value: str, key_path: str | None = None) -> int | None:
    """1-based row whose column A equals `value` (header is row 1), or None."""
    value = (value or "").strip()
    if not value:
        return None
    rows = get_values(spreadsheet_id, f"{quoted_prefix(sheet_name)}!A2:A", key_path=key_path)
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
