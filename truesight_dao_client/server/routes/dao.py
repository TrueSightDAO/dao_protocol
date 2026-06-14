"""`POST /dao/submit_contribution` — port of Rails `dao_controller#submit_contribution` (PR5b/PR5c).

Flow: verify signature → (on success) dedup by Request-Transaction-ID + record to **Telegram Chat
Logs** (synchronous, no-race) → attachment→GitHub upload → `[EMAIL REGISTERED/VERIFICATION]`
onboarding (422 on failure) → dispatch immediate processing in the background → respond.

Always logs (even failed/no-signature submissions, matching Rails). Dispatch, attachment upload,
and email onboarding only run on a verified signature.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from .. import dedup, dispatch, email_registration
from ..crypto import verify
from ..services import github_upload
from ..sheets import contributors_digital_signatures as sigs
from ..sheets import telegram_raw_log
from ..sheets import base as sheets_base

_ACAO = {"Access-Control-Allow-Origin": "*"}

router = APIRouter()

_TX_SIG_RE = re.compile(r"Request Transaction ID:\s*([A-Za-z0-9+/=]+)")

_OFFCHAIN_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"

# Events that require the signer to be a registered DAO governor
_GOVERNOR_ONLY_EVENTS = [
    "[PARTNER ADD EVENT]",
    "[DAPP PERMISSION CHANGE EVENT]",
]


def _is_governor(contributor_name: str) -> bool:
    """Check if a contributor name is registered as a DAO governor."""
    if not contributor_name:
        return False
    try:
        col = sheets_base.get_values(
            _OFFCHAIN_ID,
            f"Governors!A2:A",
            key_path=sigs._key(),
        )
        for row in col:
            if row and str(row[0]).strip().lower() == contributor_name.lower():
                return True
    except Exception:
        pass
    return False


def _has_signature_format(text: str) -> bool:
    return ("--------" in text
            and "My Digital Signature:" in text
            and "Request Transaction ID:" in text)


def _extract_tx_sig(text: str) -> str | None:
    m = _TX_SIG_RE.search(text or "")
    return m.group(1).strip() if m else None


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

    # --- dedup (only meaningful on a verified signature) ---
    if signature_verification == "success":
        tx_sig = _extract_tx_sig(text)
        if tx_sig and dedup.is_duplicate(tx_sig):
            return JSONResponse(
                {"status": "error",
                 "error": "Duplicate submission (Request Transaction ID already processed)."},
                status_code=409,
            )

        # --- governor enforcement for restricted events ---
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
    telegram_raw_log.add_record(text or "[No Text Provided]",
                                signature_verification=signature_verification)

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
        email_reg = email_registration.handle_after_successful_verify(text, verification_result)
        if email_reg.get("applicable") and email_reg.get("ok") is False:
            return JSONResponse({
                "status": "error",
                "error": email_reg.get("error") or "Email onboarding failed",
                "fileUploadedToGithub": file_uploaded,
                "googleSheetLogged": True,
                "signature_verification": signature_verification,
                "email_registration": email_reg,
            }, status_code=422)

    # --- dispatch immediate processing (background; non-user-visible propagation) ---
    if signature_verification == "success":
        background.add_task(dispatch.dispatch_event, text)

    return JSONResponse({
        "status": "success",
        "fileUploadedToGithub": file_uploaded,
        "googleSheetLogged": True,
        "signature_verification": signature_verification,
    })


@router.post("/dao/verify-signature")
async def verify_signature(request: Request) -> JSONResponse:
    """Port of Rails `dao#verify_signature` (PR8a).

    Returns `{valid, message}` on a parseable signature (valid true/false), or
    `{valid: false, error}` (422) when the input can't be verified — mirroring Rails'
    `ArgumentError → 422`. `input_text` is read from form body, query string, or JSON body
    (Rails merged all into `params`), so the POS clients' existing call shape keeps working.
    """
    input_text = ""
    try:
        form = await request.form()
        input_text = str(form.get("input_text") or "")
    except Exception:  # noqa: BLE001 — non-form body
        input_text = ""
    if not input_text:
        input_text = str(request.query_params.get("input_text") or "")
    if not input_text:
        try:
            body = await request.json()
            if isinstance(body, dict):
                input_text = str(body.get("input_text") or "")
        except Exception:  # noqa: BLE001 — non-JSON body
            pass
    try:
        result = verify.verify(input_text)
        return JSONResponse({"valid": bool(result.get("success")),
                             "message": "Signature verification successful"})
    except verify.VerificationError as e:
        return JSONResponse({"valid": False, "error": str(e)}, status_code=422)


@router.get("/dao/check_digital_signature")
async def check_digital_signature(signature: str = "") -> JSONResponse:
    """Port of Rails `dao#check_digital_signature` (PR8a).

    Public GET lookup `?signature=<SPKI base64>` → resolves the contributor by public key.
    Three response shapes (ACTIVE → registered, VERIFYING → pending, else 404), each with
    `Access-Control-Allow-Origin: *` to match Rails (the DApp/POS pages call it cross-origin).
    """
    public_key = (signature or "").strip()
    if not public_key:
        return JSONResponse({"error": "signature is required"}, status_code=400, headers=_ACAO)
    try:
        record = sigs.find_by_public_key(public_key)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"registered": False, "error": str(e)}, status_code=500, headers=_ACAO)
    if record and record.get("status") == "ACTIVE":
        return JSONResponse({"registered": True,
                             "contributor_name": record.get("name") or "",
                             "contributor_email": record.get("email") or ""}, headers=_ACAO)
    if record and record.get("status") == "VERIFYING":
        return JSONResponse({"registered": False,
                             "pending_verification": True,
                             "contributor_email": record.get("email") or ""}, headers=_ACAO)
    return JSONResponse({"registered": False,
                         "error": "No matching contributor digital signature"},
                        status_code=404, headers=_ACAO)
