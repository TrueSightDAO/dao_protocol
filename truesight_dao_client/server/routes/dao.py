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
from ..sheets import telegram_raw_log

router = APIRouter()

_TX_SIG_RE = re.compile(r"Request Transaction ID:\s*([A-Za-z0-9+/=]+)")


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
