"""`POST /dao/submit_contribution` — port of Rails `dao_controller#submit_contribution` (PR5b/PR5c).

Flow: verify signature → (on success) QR dedup for SALES EVENT (sheet-based, reversible) →
resolve governor authority (column S: YES/NO/blank) → record to **Telegram Chat
Logs** (synchronous, no-race) → attachment→GitHub upload → `[EMAIL REGISTERED/VERIFICATION]`
onboarding (422 on failure) → dispatch immediate processing in the background → respond.

Always logs (even failed/no-signature submissions, matching Rails). Dispatch, attachment upload,
and email onboarding only run on a verified signature.
"""

from __future__ import annotations

import base64
import logging
import os
import re

import httpx
import requests
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from .. import dispatch, email_registration
from ... import validators
from ..config import get_settings
from ..crypto import verify
from ..services import github_upload
from ..sheets import contributors_digital_signatures as sigs
from ..sheets import telegram_raw_log
from ..sheets import base as sheets_base

_ACAO = {"Access-Control-Allow-Origin": "*"}

router = APIRouter()

_TX_SIG_RE = re.compile(r"Request Transaction ID:\s*([A-Za-z0-9+/=]+)")

_OFFCHAIN_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"

# Agentic contributors granted governor-equivalent authority without being
# listed in the Governors tab (mirrors Rails Gdrive::Governors::TRUSTED_AGENTS).
_TRUSTED_AGENTS = {"admin@truesight.me", "truesight-autopilot"}

# Events that require the signer to be a registered DAO governor
_GOVERNOR_ONLY_EVENTS = [
    "[PARTNER ADD EVENT]",
    "[DAPP PERMISSION CHANGE EVENT]",
]

# Target Ledger values accepted for [DAO Inventory Expense Event]. Shipping,
# supplies, and operational expenses are drawn from the offchain USD balance on
# the main ledger. Managed ledgers that track their own expenses are derived
# from the treasury cache's ledgers[] array (populated from Shipment Ledger
# Listing column A). Falls back to {"offchain"} when the cache is unavailable.
def _get_valid_expense_ledgers() -> set[str]:
    ledgers = {"offchain"}
    try:
        cache = validators.fetch_treasury_cache()
        for entry in cache.get("ledgers", []):
            name = (entry.get("ledger_name") or "").strip()
            if name:
                ledgers.add(name)
    except Exception:
        pass
    return ledgers

logger = logging.getLogger("dao_protocol.dao")


def _is_governor(contributor_name: str) -> bool:
    """Check if a contributor name is registered as a DAO governor."""
    if not contributor_name:
        return False
    try:
        col = sheets_base.get_values(
            _OFFCHAIN_ID,
            "Governors!A2:A",
            key_path=sigs._key(),
        )
        for row in col:
            if row and str(row[0]).strip().lower() == contributor_name.lower():
                return True
    except Exception:
        pass
    return False


def _resolve_governor_authority(verification_result: dict | None) -> str:
    """Determine column S (governor_authority) for Telegram Chat Logs.

    Mirrors Rails `Gdrive::Governors.authority_cell_for_verification`.

    Returns 'YES' if the signer is a governor or trusted agent,
    'NO' if verified but not a governor, '' if verification failed.
    """
    if not verification_result or not verification_result.get("success"):
        return ""
    pk = verification_result.get("public_key", "")
    if not pk:
        return ""
    entry = sigs.find_by_public_key(pk)
    if not entry:
        return ""
    name = entry.get("name", "").strip()
    if not name:
        return "NO"
    if name in _TRUSTED_AGENTS:
        return "YES"
    return "YES" if _is_governor(name) else "NO"


def _resolve_sentinel_auth(verification_result: dict | None) -> str:
    """Determine column T (is_sentinel) for Telegram Chat Logs.

    Reads 'Is Sentinel' (column W) from Contributors contact information
    and returns 'TRUE' if the signer's contributor row has it set.
    Returns '' if verification failed or signer couldn't be resolved.
    """
    if not verification_result or not verification_result.get("success"):
        return ""
    pk = verification_result.get("public_key", "")
    if not pk:
        return ""
    entry = sigs.find_by_public_key(pk)
    if not entry:
        return ""
    name = entry.get("name", "").strip()
    if not name:
        return ""
    try:
        contact_prefix = sheets_base.quoted_prefix("Contributors contact information")
        # Column A (names) and column W (Is Sentinel, index 23)
        col_a = sheets_base.get_values(
            _OFFCHAIN_ID, f"{contact_prefix}!A5:A", key_path=sigs._key(),
        )
        col_w = sheets_base.get_values(
            _OFFCHAIN_ID, f"{contact_prefix}!W5:W", key_path=sigs._key(),
        )
        for i, row in enumerate(col_a):
            if row and str(row[0]).strip().lower() == name.lower():
                if i < len(col_w) and col_w[i] and str(col_w[i][0]).strip().upper() == "TRUE":
                    return "TRUE"
                break
    except Exception:
        pass
    return ""


def _has_signature_format(text: str) -> bool:
    return ("--------" in text
            and "My Digital Signature:" in text
            and "Request Transaction ID:" in text)


def _extract_tx_sig(text: str) -> str | None:
    m = _TX_SIG_RE.search(text or "")
    return m.group(1).strip() if m else None


def _extract_field(text: str, label: str) -> str | None:
    """Extract a field value from the submission text header (before the first -------- divider)."""
    norm = re.sub(r"\r\n?", "\n", text or "")
    header = norm.split("\n--------", 1)[0]
    m = re.search(rf"(?im)^-\s*{re.escape(label)}:\s*(.+)$", header)
    return m.group(1).strip() if m else None


def _safe_hash(hash_key: str) -> str:
    """Filesystem-safe form of a Scoring Hash Key — must match generate_review_cache.py."""
    return hash_key.replace("/", "_").replace("+", "-").replace("=", "")


def _delete_cache_file(hash_key: str) -> bool:
    """Delete the review-queue cache file(s) for a Scoring Hash Key.

    Cache files are named ``<safe_hash>__<sheet_row>.json`` (see generate_review_cache.py):
    the raw hash isn't filesystem-safe and isn't unique per row (splits share a hash). So we
    list ``review-queue/`` and delete every file whose name starts with ``<safe_hash>__`` (plus
    the legacy ``<hash_key>.json`` name, if any). A still-pending split sibling is re-created on
    the next generator run. Returns True if all matches were deleted or none existed.
    """
    settings = get_settings()
    pat = settings.github_pat
    if not pat:
        logger.warning("No github_pat configured — cannot delete cache file for %s", hash_key)
        return False

    repo = settings.github_review_queue_repo
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    list_api = f"https://api.github.com/repos/{repo}/contents/review-queue"
    prefix = f"{_safe_hash(hash_key)}__"
    legacy = f"{hash_key}.json"

    try:
        list_resp = requests.get(list_api, headers=headers, timeout=20)
        if list_resp.status_code == 404:
            return True  # directory gone — nothing to delete
        if list_resp.status_code != 200:
            logger.warning("GitHub list review-queue returned %d", list_resp.status_code)
            return False

        entries = list_resp.json()
        targets = [
            e for e in entries
            if isinstance(e, dict) and (e.get("name", "").startswith(prefix) or e.get("name", "") == legacy)
        ]
        if not targets:
            return True  # already processed / never cached

        all_ok = True
        for e in targets:
            del_resp = requests.delete(
                f"https://api.github.com/repos/{repo}/contents/{e['path']}",
                headers=headers, timeout=15,
                json={
                    "message": f"Review processed: delete cache {e['name']}",
                    "sha": e["sha"],
                    "branch": "main",
                },
            )
            if del_resp.status_code not in (200, 204):
                logger.warning("GitHub DELETE %s returned %d", e["name"], del_resp.status_code)
                all_ok = False
        return all_ok
    except requests.RequestException as exc:
        logger.warning("GitHub API error deleting cache for %s: %s", hash_key, exc)
        return False


def _call_gas_review_webhook() -> bool:
    """Call the GAS webhook to trigger processApprovalRejections.

    Retries up to 3 times with exponential backoff on non-200.
    """
    settings = get_settings()
    url = settings.gas_review_webhook_url
    if not url:
        logger.warning("No gas_review_webhook_url configured — GAS cron will process")
        return False

    import time
    for attempt in range(3):
        try:
            resp = requests.get(url, params={"exec": "processApprovalRejections"}, timeout=30)
            if resp.status_code == 200:
                return True
            logger.warning("GAS webhook attempt %d returned %d", attempt + 1, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("GAS webhook attempt %d failed: %s", attempt + 1, exc)
        if attempt < 2:
            time.sleep(2 ** attempt)  # 1s, 2s
    return False


def _generate_transaction_id() -> str:
    """Generate a unique transaction ID for tracking review events."""
    from datetime import datetime, timezone
    import random
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = random.randint(1000, 9999)
    return f"REV-{ts}-{rand}"


@router.get("/dao/check_digital_signature")
async def check_digital_signature(
    signature: str = Query(..., description="Base64 DER SPKI public key"),
) -> JSONResponse:
    """Port of Rails dao_controller#check_digital_signature.

    Returns registration status + contributor info for a public key.
    """
    pk = signature.strip()
    if not pk:
        return JSONResponse({"registered": False, "error": "Missing signature parameter"}, status_code=400)
    entry = sigs.find_by_public_key(pk)
    if not entry:
        return JSONResponse({"registered": False, "error": "No matching contributor digital signature"}, status_code=404)
    status = entry.get("status", "")
    if status == "ACTIVE":
        return JSONResponse({
            "registered": True,
            "contributor_name": entry.get("name", ""),
            "contributor_email": entry.get("email", ""),
        }, headers=_ACAO)
    if status == "VERIFYING":
        return JSONResponse({
            "registered": False,
            "pending_verification": True,
            "contributor_email": entry.get("email", ""),
        }, headers=_ACAO)
    return JSONResponse({"registered": False, "error": f"Unknown status: {status}"}, status_code=404)


@router.post("/dao/submit_contribution")
async def submit_contribution(request: Request, background: BackgroundTasks) -> JSONResponse:
    form = await request.form()
    text = str(form.get("text") or "").strip()
    attachment = form.get("attachment")

    # --- verify ---
    signature_verification = "not_attempted"
    verification_result = None
    if _has_signature_format(text):
        try:
            verification_result = verify.verify(text)
            signature_verification = "success" if verification_result.get("success") else "failed"
        except verify.VerificationError:
            signature_verification = "error"
        except Exception:
            signature_verification = "error"
    else:
        signature_verification = "no_signature_format"

    # --- QR dedup for SALES EVENT (sheet-based, reversible) ---
    if signature_verification == "success" and "[SALES EVENT]" in text:
        qr = _extract_field(text, "QR Code")
        if qr:
            from ..sheets import qr_code_sales
            if qr_code_sales.already_recorded(qr):
                return JSONResponse(
                    {"status": "error",
                     "error": f"QR code {qr} already has a sales record in QR Code Sales. "
                              f"To re-submit, delete the row from the QR Code Sales sheet first."},
                    status_code=409,
                )

    # --- Target Ledger validation for DAO Inventory Expense Event ---
    if signature_verification == "success" and "[DAO Inventory Expense Event]" in text:
        ledger = (_extract_field(text, "Target Ledger") or "").strip()
        if ledger not in _get_valid_expense_ledgers():
            valid = sorted(_get_valid_expense_ledgers())
            return JSONResponse(
                {"status": "error",
                 "error": f"Invalid Target Ledger '{ledger or '(empty)'}' for expense. "
                           f"Accepted ledgers: {', '.join(valid)}."},
                status_code=422,
            )

    # --- governor enforcement for restricted events ---
    if signature_verification == "success":
        for gov_event in _GOVERNOR_ONLY_EVENTS:
            if gov_event in text:
                pk = verification_result.get("public_key", "") if verification_result else ""
                entry = sigs.find_by_public_key(pk) if pk else None
                name = entry.get("name", "") if entry else ""
                if not _is_governor(name):
                    return JSONResponse({
                        "status": "error",
                        "error": f"Only DAO governors may submit {gov_event}. "
                                 f"Signer '{name or 'unknown'}' is not a registered governor.",
                        "signature_verification": signature_verification,
                    }, status_code=403)
                break

    # --- log to Telegram Chat Logs (synchronous; user-visible state, no-race rule) ---
    governor_authority = _resolve_governor_authority(
        verification_result if signature_verification == "success" else None
    )
    is_sentinel = _resolve_sentinel_auth(
        verification_result if signature_verification == "success" else None
    )
    telegram_raw_log.add_record(text or "[No Text Provided]",
                                signature_verification=signature_verification,
                                governor_authority=governor_authority,
                                is_sentinel=is_sentinel)

    # --- attachment → GitHub upload (when text references a github.com blob/tree URL) ---
    file_uploaded = False
    if attachment is not None and hasattr(attachment, "read"):
        try:
            file_bytes = await attachment.read()
            file_uploaded = github_upload.upload_if_referenced(
                text, file_bytes, getattr(attachment, "filename", None)
            )
        except Exception:
            file_uploaded = False

    # --- email onboarding ([EMAIL REGISTERED] / [EMAIL VERIFICATION]) ---
    if signature_verification == "success":
        email_result = email_registration.handle_after_successful_verify(text, verification_result)
    else:
        email_result = None

    # --- dispatch immediate processing in background ---
    if signature_verification == "success":
        background.add_task(dispatch.dispatch_event, text)

    return JSONResponse({
        "status": "ok",
        "signature_verification": signature_verification,
        "fileUploadedToGithub": file_uploaded,
        "emailRegistration": email_result,
    }, headers=_ACAO)


@router.post("/dao/submit_contribution_review")
async def submit_contribution_review(request: Request, background: BackgroundTasks) -> JSONResponse:
    """Handle [CONTRIBUTION REVIEW EVENT] submissions.

    Flow:
    1. Verify RSA signature
    2. Check signer is governor or Sentinel (403 otherwise)
    3. Validate required fields (Action, Scoring Hash Key)
    4. Delete the cache file from treasury-cache/review-queue/
    5. Append the review event to Telegram Chat Logs
    6. Call GAS webhook to trigger processApprovalRejections
    """
    form = await request.form()
    text = str(form.get("text") or "").strip()

    if not text:
        return JSONResponse({"status": "error", "error": "Missing text field"}, status_code=400, headers=_ACAO)

    # --- verify signature ---
    if not _has_signature_format(text):
        return JSONResponse({
            "status": "error",
            "error": "Missing signature format (-------- / My Digital Signature: / Request Transaction ID:)",
        }, status_code=400, headers=_ACAO)

    try:
        verification_result = verify.verify(text)
    except verify.VerificationError as exc:
        return JSONResponse({"status": "error", "error": f"Signature verification failed: {exc}"},
                            status_code=401, headers=_ACAO)
    except Exception as exc:
        return JSONResponse({"status": "error", "error": f"Signature verification error: {exc}"},
                            status_code=500, headers=_ACAO)

    if not verification_result.get("success"):
        return JSONResponse({"status": "error", "error": "Signature verification failed"},
                            status_code=401, headers=_ACAO)

    # --- resolve signer identity ---
    pk = verification_result.get("public_key", "")
    entry = sigs.find_by_public_key(pk) if pk else None
    signer_name = entry.get("name", "").strip() if entry else ""
    signer_email = entry.get("email", "").strip() if entry else ""

    if not signer_name:
        return JSONResponse({"status": "error", "error": "Could not resolve signer identity"},
                            status_code=403, headers=_ACAO)

    # --- check governor or Sentinel authority ---
    is_governor = signer_name in _TRUSTED_AGENTS or _is_governor(signer_name)
    is_sentinel = _resolve_sentinel_auth(verification_result) == "TRUE"

    if not is_governor and not is_sentinel:
        return JSONResponse({
            "status": "error",
            "error": f"Only governors and Sentinels may submit review events. "
                     f"Signer '{signer_name}' is not authorized.",
        }, status_code=403, headers=_ACAO)

    # --- extract fields ---
    action = _extract_field(text, "Action")
    scoring_hash_key = _extract_field(text, "Scoring Hash Key")
    tdg_issued = _extract_field(text, "TDGs Issued")
    rejection_reason = _extract_field(text, "Rejection Reason")
    contributor_name = _extract_field(text, "Contributor Name")

    # --- validate required fields ---
    if not action:
        return JSONResponse({"status": "error", "error": "Missing Action field"},
                            status_code=400, headers=_ACAO)
    if not scoring_hash_key:
        return JSONResponse({"status": "error", "error": "Missing Scoring Hash Key field"},
                            status_code=400, headers=_ACAO)

    action_upper = action.upper()
    if action_upper == "APPROVE" and not tdg_issued:
        return JSONResponse({"status": "error", "error": "Approve requires TDGs Issued field"},
                            status_code=400, headers=_ACAO)
    if action_upper == "REJECT" and not rejection_reason:
        return JSONResponse({"status": "error", "error": "Reject requires Rejection Reason field"},
                            status_code=400, headers=_ACAO)

    # --- validate the reviewed contributor at the trust boundary ---
    # On Approve the Contributor Name is written to Scored Chatlogs Col A and decides who
    # receives the TDG. Block unknown / hallucinated / typo'd names here so a hallucinating
    # LLM, Sophia, or any client POSTing directly cannot inject a false contributor. The
    # validator checks against the DAO members roster (Contributors contact information Col A)
    # and only degrades to "allow" if that cache is unreachable — the GAS write-back's
    # (hash+contributor) match and the transfer script's contributor validation remain the
    # downstream backstop.
    if action_upper == "APPROVE" and contributor_name:
        try:
            validators.dao_contributor_name(contributor_name)
        except ValueError as exc:
            return JSONResponse({
                "status": "error",
                "error": f"Unknown contributor for review approval: {exc}",
            }, status_code=422, headers=_ACAO)

    # --- generate transaction ID ---
    transaction_id = _generate_transaction_id()

    # --- delete cache file ---
    cache_deleted = _delete_cache_file(scoring_hash_key)
    if not cache_deleted:
        logger.warning("Cache file deletion failed or already gone for %s — continuing", scoring_hash_key)

    # --- append to Telegram Chat Logs ---
    # Build a record that includes the review event details, reviewer email, and transaction ID
    review_record = (
        f"[CONTRIBUTION REVIEW EVENT]\n"
        f"- Action: {action}\n"
        f"- Scoring Hash Key: {scoring_hash_key}\n"
        f"- TDGs Issued: {tdg_issued or '0.00'}\n"
        f"- Rejection Reason: {rejection_reason or ''}\n"
        f"- Reviewer Email: {signer_email}\n"
        f"- Transaction ID: {transaction_id}\n"
        f"--------\n"
        f"My Digital Signature: (verified)\n"
        f"Request Transaction ID: {transaction_id}"
    )

    governor_authority = "YES" if is_governor else "NO"
    is_sentinel_str = "TRUE" if is_sentinel else ""
    telegram_raw_log.add_record(review_record,
                                signature_verification="success",
                                governor_authority=governor_authority,
                                is_sentinel=is_sentinel_str)

    # --- call GAS webhook in background ---
    background.add_task(_call_gas_review_webhook)

    return JSONResponse({
        "status": "ok",
        "action": action,
        "scoring_hash_key": scoring_hash_key,
        "transaction_id": transaction_id,
        "cache_deleted": cache_deleted,
    }, headers=_ACAO)
