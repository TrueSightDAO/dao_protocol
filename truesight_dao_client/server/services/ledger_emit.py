"""Emit verified RSA-signed submissions to the public attestation ledger
(TrueSightDAO/verify_public_signatures) at verify time.

Design (plan A4): every event Edgar *verifies* gets an immutable, self-verifying
JSON file in the public ledger — `tree_planting/171.json` etc. — keyed by the
same Telegram message_id the 30-min reconciliation cron uses, so the cron heals
any emit gap and emits are idempotent (GET-before-PUT per file). Fail-closed:
never publish if the signed text contains email/PII patterns, and never publish
event types that aren't yet mapped to a ledger folder (EMAIL REGISTERED /
VERIFICATION stay out — their signed_text carries farmer emails).

Field names mirror the cron's record schema exactly (schema_version 1), so a
ledger file is indistinguishable whether written by the emit hook or the cron.
"""

from __future__ import annotations

import base64
import json
import logging
import re

import requests

from ..config import get_settings
from ..sheets import contributors_digital_signatures as sigs

logger = logging.getLogger("dao_protocol.ledger_emit")

# Event marker -> ledger folder (must match the cron + README layout).
_FOLDER_BY_MARKER = {
    "[TREE PLANTING EVENT]": "tree_planting",
    "[TREE PLANTING LINK EVENT]": "tree_planting_link",
    "[TREE PLANTING REJECT EVENT]": "tree_planting_reject",
    "[TREE GROWTH MONITORING EVENT]": "tree_growth_monitoring",
}

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
# Known non-PII substrings that trip the naive email regex (e.g. sample strings).
_EMAIL_ALLOW = {"example.com", "test.com", "truesight.me", "agroverse.io"}


def _has_pii(text: str) -> bool:
    """Fail-closed PII scan: True if the text looks like it carries an email."""
    for m in _EMAIL_RE.finditer(text or ""):
        domain = m.group(0).rsplit("@", 1)[-1].lower()
        if domain not in _EMAIL_ALLOW:
            return True
    return False


def _folder_for(text: str) -> str | None:
    for marker, folder in _FOLDER_BY_MARKER.items():
        if marker in (text or ""):
            return folder
    return None


def _resolve_contributor(public_key_pem: str) -> str:
    try:
        entry = sigs.find_by_public_key(public_key_pem)
        return (entry or {}).get("name", "") or ""
    except Exception:
        return ""


def _put_file(pat: str, repo: str, path: str, content: dict) -> bool:
    """GET-before-PUT Contents-API write (idempotent; skip if already present)."""
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    try:
        get = requests.get(api, headers=headers, timeout=30)
        if get.status_code == 200:
            return True  # already emitted — idempotent
        if get.status_code != 404:
            logger.warning("ledger GET %s for %s (%s)", get.status_code, path, repo)
            return False
        put = requests.put(api, headers=headers, timeout=60, json={
            "message": f"Emit {path} (verified signature)",
            "content": base64.b64encode(json.dumps(content, indent=2).encode("utf-8")).decode("ascii"),
            "branch": "main",
        })
        if put.status_code in (200, 201):
            return True
        logger.warning("ledger PUT %s for %s (%s)", put.status_code, path, repo)
        return False
    except requests.RequestException as exc:
        logger.warning("ledger emit failed for %s: %s", path, exc)
        return False


def emit(text: str, verification_result: dict, message_id: str) -> bool:
    """Publish one verified event to the public ledger. Non-fatal on any failure.

    Returns True if the file is present (written now or already existed).
    Never raises — the submission flow must not depend on the ledger.
    """
    if not text or not verification_result or not message_id:
        return False
    if not verification_result.get("success"):
        return False
    folder = _folder_for(text)
    if not folder:
        return False  # not a ledger-mapped event (EMAIL REGISTERED etc.)
    if _has_pii(text):
        logger.warning("ledger emit skipped (PII in text) for %s", message_id)
        return False

    settings = get_settings()
    pat = settings.github_ledger_pat or settings.github_pat
    repo = settings.github_ledger_repo or "TrueSightDAO/verify_public_signatures"
    if not pat:
        return False

    record = {
        "event_type": next(k for k in _FOLDER_BY_MARKER if k in text),
        "telegram_message_id": message_id,
        "telegram_update_id": message_id,
        "submitted_at": _now_iso(),
        "contributor_name": _resolve_contributor(verification_result.get("public_key", "")),
        "public_key": verification_result.get("public_key", ""),
        "signature": verification_result.get("signature", ""),
        "signed_payload": verification_result.get("payload", ""),
        "signed_text": text,
        "source_tab": "Telegram Chat Logs",
        "verifiable": True,
        "linked_tree_id": "",
    }
    return _put_file(pat, repo, f"{folder}/{message_id}.json", record)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
