"""Port of Rails `DaoEmailRegistrationService` — handles `[EMAIL REGISTERED]` / `[EMAIL
VERIFICATION]` after a verified `/dao` submission. REGISTERED → append a VERIFYING row +
send the GAS verification email; VERIFICATION → single-use consume (VERIFYING→ACTIVE).

**Resend support (2026-06-08):** When a re-submitted `[EMAIL REGISTERED EVENT]` is signed by a
key that is already **VERIFYING**, re-send the verification email using the existing `vk`
instead of skipping silently. Gated by a 60s cooldown per row (column I). ACTIVE keys still
skip (already verified).

Runs synchronously; returns a structured dict (`applicable`/`ok`/`event`/…) for the response.

After a successful `consume_verification` we also fire the GAS `refresh_dao_members_cache` action
(the same publisher as the verification mailer — Rails' `DaoMembersCacheRefreshWorker`). Without
this, the sheet shows ACTIVE but the dapp's "is registered" check (which reads the GitHub-raw
`dao_members.json` cache) still says no, so a freshly-verified user sees "digital signature not
registered" right after clicking the verification link. Best-effort: cache failure is logged but
does not fail the response — activation itself is complete on the sheet.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone

import requests

from .config import get_settings
from .sheets import contributors_digital_signatures as cds

logger = logging.getLogger("dao_protocol.email_registration")
_DEFAULT_RETURN_URL = "https://truesightdao.github.io/dapp/create_signature.html"
_RESEND_COOLDOWN_SECONDS = 60


def handle_after_successful_verify(text: str, verification_result: dict | None) -> dict:
    if not text or not (isinstance(verification_result, dict) and verification_result.get("success")):
        return {"applicable": False}
    try:
        if "[EMAIL REGISTERED EVENT]" in text:
            return {"applicable": True, **_process_registration(text, verification_result)}
        if "[EMAIL VERIFICATION EVENT]" in text:
            return {"applicable": True, **_process_verification(text, verification_result)}
        return {"applicable": False}
    except Exception as exc:
        event = "EMAIL_VERIFICATION" if "[EMAIL VERIFICATION EVENT]" in text else "EMAIL_REGISTERED"
        logger.error("email_registration error: %s", exc)
        return {"applicable": True, "ok": False, "event": event, "error": str(exc)}


def _extract_field(text: str, label: str) -> str | None:
    norm = re.sub(r"\r\n?", "\n", text or "")
    header = norm.split("\n--------", 1)[0]
    m = re.search(rf"(?im)^-\s*{re.escape(label)}:\s*(.+)$", header)
    return m.group(1).strip() if m else None


def _pubkey_for_sheet(verification_result: dict, text: str) -> str:
    pem = verification_result.get("public_key") if isinstance(verification_result, dict) else None
    if pem:
        canon = cds.normalize_public_key(pem)
        if canon:
            return canon
    norm = re.sub(r"\r\n?", "\n", text or "")
    m = re.search(r"My Digital Signature:\s*([A-Za-z0-9+/=\s]+?)(?:\n\n|\nRequest Transaction ID:)", norm)
    return cds.normalize_public_key(m.group(1)) if m else ""


def _generation_source_url(text: str) -> str | None:
    m = re.search(r"This submission was generated using\s+(\S+)", text or "")
    return m.group(1).strip() if m else None


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse a sheet timestamp string (e.g. '2026-06-08 12:34:56') into a datetime.
    Returns None if unparseable."""
    if not ts or not ts.strip():
        return None
    try:
        # Try the standard format first
        return datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        # Try the legacy format (no spaces, e.g. '20250706 15:50:30')
        return datetime.strptime(ts.strip(), "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


def _process_registration(text: str, vr: dict) -> dict:
    email = (_extract_field(text, "Email") or "").lower().strip()
    if not email or "@" not in email:
        return {"ok": False, "event": "EMAIL_REGISTERED", "error": "Invalid or missing email address."}
    pk = _pubkey_for_sheet(vr, text)
    if not pk:
        return {"ok": False, "event": "EMAIL_REGISTERED", "error": "Could not read digital signature from submission."}

    existing = cds.find_by_public_key(pk)
    if existing:
        status = existing.get("status", "")
        if status == "ACTIVE":
            return {"ok": True, "event": "EMAIL_REGISTERED", "skipped": True,
                    "reason": "public_key_already_active",
                    "email": existing.get("email") or email, "verification_email_sent": False}
        if status == "VERIFYING":
            # Resend path: reuse existing vk, gate by cooldown
            sheet_row = existing.get("row")
            existing_vk = existing.get("vk", "")
            if not sheet_row or not existing_vk:
                return {"ok": False, "event": "EMAIL_REGISTERED",
                        "error": "Could not read existing verification key for resend."}

            # Check cooldown
            last_sent = cds.get_email_last_sent(sheet_row)
            if last_sent:
                last_dt = _parse_timestamp(last_sent)
                if last_dt:
                    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if elapsed < _RESEND_COOLDOWN_SECONDS:
                        retry_after = int(_RESEND_COOLDOWN_SECONDS - elapsed) + 1
                        logger.info(
                            "EMAIL REGISTERED: resend cooldown active for row=%s "
                            "(elapsed=%.0fs, retry_after=%ds)",
                            sheet_row, elapsed, retry_after
                        )
                        return {"ok": True, "event": "EMAIL_REGISTERED",
                                "resent": False, "cooldown": True,
                                "retry_after_s": retry_after,
                                "email": existing.get("email") or email}

            # Cooldown passed or no prior send — re-send the email
            gas = _trigger_verification_email(
                existing.get("email") or email,
                existing_vk,
                _generation_source_url(text)
            )
            if not gas.get("ok"):
                return {"ok": False, "event": "EMAIL_REGISTERED",
                        "error": gas.get("error") or "Verification email could not be resent."}

            # Stamp last-sent timestamp
            cds.update_email_last_sent(sheet_row)
            logger.info("EMAIL REGISTERED: resent verification email for row=%s", sheet_row)
            return {"ok": True, "event": "EMAIL_REGISTERED",
                    "resent": True, "cooldown": False,
                    "email": existing.get("email") or email,
                    "verification_email_sent": True,
                    "skipped": False}

    # No existing row — fresh registration
    vk = secrets.token_urlsafe(32)
    if not cds.append_pending_row(email, pk, vk):
        return {"ok": False, "event": "EMAIL_REGISTERED", "error": "Failed to append Contributors Digital Signatures row."}

    gas = _trigger_verification_email(email, vk, _generation_source_url(text))
    if not gas.get("ok"):
        return {"ok": False, "event": "EMAIL_REGISTERED", "error": gas.get("error") or "Verification email could not be sent."}

    # Stamp last-sent on the newly appended row (find it by pk)
    fresh = cds.find_by_public_key(pk)
    if fresh and fresh.get("row"):
        cds.update_email_last_sent(fresh["row"])

    return {"ok": True, "event": "EMAIL_REGISTERED", "email": email,
            "verification_email_sent": True, "skipped": False}


def _process_verification(text: str, vr: dict) -> dict:
    pk = _pubkey_for_sheet(vr, text)
    vk = cds.normalize_verification_key(_extract_field(text, "Verification Key") or "")
    email = (_extract_field(text, "Email") or "").lower().strip()
    if not pk or not vk:
        return {"ok": False, "event": "EMAIL_VERIFICATION", "error": "Could not read digital signature or verification key."}

    result = cds.consume_verification(pk, vk, email or None)
    outcome = result.get("outcome")
    if outcome == "activated":
        cache = _trigger_dao_members_cache_refresh()
        if not cache.get("ok"):
            logger.warning("dao_members cache refresh failed after activation: %s", cache.get("error"))
        return {"ok": True, "event": "EMAIL_VERIFICATION", "activated": True,
                "cache_refresh": bool(cache.get("ok"))}
    if outcome == "already_consumed_same_key":
        return {"ok": True, "event": "EMAIL_VERIFICATION", "activated": False, "already_consumed": True}
    if outcome == "pubkey_mismatch":
        return {"ok": False, "event": "EMAIL_VERIFICATION",
                "error": "This verification link was already used from a different device. "
                         "Start a new registration from create_signature.html."}
    if outcome == "not_found":
        return {"ok": False, "event": "EMAIL_VERIFICATION",
                "error": "No matching pending verification row (check verification key or wait for sheet sync)."}
    return {"ok": False, "event": "EMAIL_VERIFICATION", "error": result.get("error") or "Verification processing failed."}


def _gas_json_ok(resp) -> bool:
    try:
        if not (200 <= resp.status_code < 300):
            return False
        parsed = resp.json()
        return isinstance(parsed, dict) and parsed.get("ok") is True
    except Exception:
        return False


# Bounded retry for the cache-refresh fan-out. The Rails original ran on Sidekiq with
# retry backoff specifically to ride out GAS cold starts / transient 5xx; mirror that here
# so a single transient failure doesn't leave dao_members.json stale until the daily 03:00
# cron. Waits sit between attempts → 3 attempts total (immediate, +2s, +6s).
_CACHE_REFRESH_BACKOFFS_S = (2, 6)
_CACHE_REFRESH_TIMEOUT_S = 30


def _trigger_dao_members_cache_refresh() -> dict:
    """Port of Rails `DaoMembersCacheRefreshWorker` — reuses the email-verification GAS publisher
    (same Apps Script project) with `action=refresh_dao_members_cache`. Best-effort with bounded
    retries (3 attempts, 2s/6s backoff) so a transient GAS cold-start/5xx doesn't leave
    dao_members.json stale until the daily cron; caller logs the final failure and proceeds (the
    sheet activation is independent)."""
    s = get_settings()
    url = (s.email_verification_gas_webhook_url or "").strip()
    secret = (s.email_verification_gas_secret or "").strip()
    if not url or not secret:
        return {"ok": False, "error": "EMAIL_VERIFICATION_GAS_WEBHOOK_URL / SECRET not set on the server."}
    headers = {"User-Agent": "TrueSight-dao_protocol/DaoMembersCacheRefresh"}
    attempts = len(_CACHE_REFRESH_BACKOFFS_S) + 1
    last_err = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(_CACHE_REFRESH_BACKOFFS_S[attempt - 1])
        try:
            resp = requests.get(url.rstrip("/"),
                                params={"action": "refresh_dao_members_cache", "secret": secret},
                                timeout=_CACHE_REFRESH_TIMEOUT_S, headers=headers, allow_redirects=True)
            if _gas_json_ok(resp):
                return {"ok": True, "attempts": attempt + 1}
            last_err = f"GAS cache refresh HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last_err = str(exc)
        logger.info("dao_members cache refresh attempt %d/%d failed: %s", attempt + 1, attempts, last_err)
    return {"ok": False, "error": last_err, "attempts": attempts}


def _trigger_verification_email(email: str, verification_key: str, return_url: str | None) -> dict:
    s = get_settings()
    url = (s.email_verification_gas_webhook_url or "").strip()
    secret = (s.email_verification_gas_secret or "").strip()
    if not url or not secret:
        return {"ok": False, "error": "EMAIL_VERIFICATION_GAS_WEBHOOK_URL / SECRET not set on the server."}
    base_url = url.rstrip("/")
    ret = return_url or _DEFAULT_RETURN_URL
    headers = {"User-Agent": "TrueSight-dao_protocol/EmailVerification"}
    try:
        g = requests.get(base_url, params={"action": "sendEmailVerification", "secret": secret,
                                           "email": email, "verification_key": verification_key, "return_url": ret},
                         timeout=20, headers=headers, allow_redirects=True)
        if _gas_json_ok(g):
            return {"ok": True}
        p = requests.post(base_url, data=json.dumps({"secret": secret, "email": email,
                                                     "verification_key": verification_key, "return_url": ret}),
                          headers={**headers, "Content-Type": "application/json"}, timeout=20, allow_redirects=True)
        if _gas_json_ok(p):
            return {"ok": True}
        return {"ok": False, "error": f"GAS verification email failed (GET {g.status_code} / POST {p.status_code})."}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}
