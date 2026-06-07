"""Port of Rails `Gdrive::ContributorsDigitalSignatures` (the email-onboarding sheet ops) — built
from `dapp_digital_signature_onboarding/demo_edgar_digital_signature_sheet_flow.py` plus the real
model's col-H ("Verification Key Consumed") logic.

Tab "Contributors Digital Signatures" (cols A–H): A Name · B Created · C Last Active · D Status ·
E Signature(=SPKI public key) · F Email · G Verification Key · H Verification Key Consumed.
Single-use verification: `consume_verification` flips VERIFYING→ACTIVE and stamps H. Uses the
default service-account key (same workbook as the other Edgar Gdrive tabs)."""

from __future__ import annotations

import base64
import urllib.parse
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization

from ..config import get_settings
from . import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
SHEET = "Contributors Digital Signatures"
CONTACT_SHEET = "Contributors contact information"

COL_NAME, COL_CREATED, COL_LAST_ACTIVE, COL_STATUS = 1, 2, 3, 4
COL_SIGNATURE, COL_EMAIL, COL_VERIFICATION_KEY, COL_VK_CONSUMED = 5, 6, 7, 8


def _key() -> str:
    return get_settings().google_sa_json


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def normalize_public_key(value) -> str:
    raw = str(value or "").replace("​", "").replace("﻿", "").strip()
    if not raw:
        return ""
    pemish = raw.replace("\r\n", "\n").replace("\r", "\n")
    if "BEGIN" in pemish and "PUBLIC KEY" in pemish:
        try:
            key = serialization.load_pem_public_key(pemish.encode("utf-8"))
            der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            return base64.b64encode(der).decode("ascii")
        except Exception:
            pass
    return "".join(raw.split())


def normalize_verification_key(value) -> str:
    s = str(value or "").strip()
    if not s:
        return s
    return urllib.parse.unquote_plus(s) if "%" in s else s


def _fetch_row_a_h(row: int) -> list:
    vals = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A{row}:H{row}", key_path=_key())
    return vals[0] if vals else []


def lookup_contributor_name(email: str) -> str:
    em = (email or "").lower().strip()
    if "@" not in em:
        return ""
    cprefix = base.quoted_prefix(CONTACT_SHEET)
    col = base.get_values(SPREADSHEET_ID, f"{cprefix}!D2:D", key_path=_key())
    for idx, row in enumerate(col):
        if row and str(row[0]).lower().strip() == em:
            a = base.get_values(SPREADSHEET_ID, f"{cprefix}!A{idx + 2}:A{idx + 2}", key_path=_key())
            return str(a[0][0]).strip() if a and a[0] else ""
    return ""


def _rows_matching_public_key(public_key_b64: str) -> list[int]:
    pk = normalize_public_key(public_key_b64)
    if not pk:
        return []
    col = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!E2:E", key_path=_key())
    return [i + 2 for i, row in enumerate(col) if row and normalize_public_key(row[0]) == pk]


def _rows_matching_verification_key(vk: str) -> list[int]:
    vk = normalize_verification_key(vk)
    if not vk:
        return []
    col = base.get_values(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!G2:G", key_path=_key())
    return [i + 2 for i, row in enumerate(col) if row and normalize_verification_key(row[0]) == vk]


def find_by_public_key(public_key_b64: str) -> dict | None:
    """Prefer an ACTIVE row, else the newest VERIFYING. Returns {row, status, name, email} or None.

    `name` (col A "Contributor Name") is included for the public `check_digital_signature`
    lookup, which echoes the contributor's name back to the DApp / POS clients.
    """
    rows = _rows_matching_public_key(public_key_b64)
    if not rows:
        return None
    for r in rows:  # any ACTIVE
        row = _fetch_row_a_h(r)
        if base.cell(row, COL_STATUS).strip().upper() == "ACTIVE":
            return {"row": r, "status": "ACTIVE",
                    "name": base.cell(row, COL_NAME).strip(),
                    "email": base.cell(row, COL_EMAIL).strip()}
    for r in reversed(rows):  # newest VERIFYING
        row = _fetch_row_a_h(r)
        if base.cell(row, COL_STATUS).strip().upper() == "VERIFYING":
            return {"row": r, "status": "VERIFYING",
                    "name": base.cell(row, COL_NAME).strip(),
                    "email": base.cell(row, COL_EMAIL).strip()}
    return None


def append_pending_row(email: str, public_key: str, verification_key: str) -> bool:
    try:
        name = lookup_contributor_name(email)
        now = _now()
        row = [name, now, now, "VERIFYING", normalize_public_key(public_key),
               email.lower().strip(), str(verification_key or "")]
        base.append_row(SPREADSHEET_ID, f"{base.quoted_prefix(SHEET)}!A:G", row, key_path=_key())
        return True
    except Exception:
        return False


def consume_verification(public_key_b64: str, verification_key: str, email: str | None = None) -> dict:
    """Single-use VK consumption. Outcomes: activated | already_consumed_same_key | pubkey_mismatch
    | not_found | error (mirrors Rails consume_verification!)."""
    pk = normalize_public_key(public_key_b64)
    vk = normalize_verification_key(verification_key)
    if not pk or not vk:
        return {"outcome": "not_found"}
    try:
        rows = _rows_matching_verification_key(vk)
        if not rows:
            return {"outcome": "not_found"}
        sheet_row = max(rows)  # vk unique; newest wins
        row = _fetch_row_a_h(sheet_row)
        if not row:
            return {"outcome": "not_found"}
        if normalize_public_key(base.cell(row, COL_SIGNATURE)) != pk:
            return {"outcome": "pubkey_mismatch", "row": sheet_row}
        if base.cell(row, COL_VK_CONSUMED).strip():
            return {"outcome": "already_consumed_same_key", "row": sheet_row}

        now = _now()
        full = list(row) + [""] * (COL_VK_CONSUMED - len(row))
        full[COL_LAST_ACTIVE - 1] = now
        full[COL_STATUS - 1] = "ACTIVE"
        full[COL_VK_CONSUMED - 1] = now
        base.sheets_service(_key()).spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f"{base.quoted_prefix(SHEET)}!A{sheet_row}:H{sheet_row}",
            valueInputOption="USER_ENTERED", body={"values": [full]},
        ).execute()
        return {"outcome": "activated", "row": sheet_row}
    except Exception as exc:
        return {"outcome": "error", "error": str(exc)}
