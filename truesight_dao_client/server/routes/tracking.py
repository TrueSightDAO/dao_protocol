"""Newsletter + Email-Agent open/click tracking — port of Rails NewsletterController
and EmailAgentController (PR3).

Routes:
  GET /newsletter/open.gif?mid=<uuid>&r=<b64url recipient>
  GET /newsletter/click?mid=<uuid>&r=<b64url recipient>&to=<b64url url>
  GET /email_agent/open.gif?tid=<suggestion_id>
  GET /email_agent/click?tid=<suggestion_id>&r=<b64url recipient>&to=<b64url url>

Contract (matches Rails): always 302-redirect (open → branded logo; click → target or
fallback), never depend on auth, no-cache headers, and the Sheets write is best-effort —
a Sheets/credential error must never break the redirect.
"""

from __future__ import annotations

import base64
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..sheets import email_agent_drafts, newsletter_emails

router = APIRouter()

OPEN_TRACKING_LOGO_URL = (
    "https://raw.githubusercontent.com/TrueSightDAO/.github/main/assets/"
    "20230711%20-%20Agroverse%20logo%20for%20trademark%20filing.jpeg"
)
CLICK_FALLBACK_URL = "https://www.agroverse.shop"
_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _decode_b64(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    try:
        pad = "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s + pad).decode("utf-8")
    except Exception:
        return None


def _safe_redirect_url(url: str | None) -> str | None:
    """Only http(s) with a host — blocks javascript:/data:/file: open-redirect abuse."""
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return url
    except Exception:
        pass
    return None


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=302, headers=dict(_NO_CACHE))


@router.get("/newsletter/open.gif")
async def newsletter_open(request: Request) -> RedirectResponse:
    mid = (request.query_params.get("mid") or "").strip()
    recipient = _decode_b64(request.query_params.get("r"))
    if mid:
        try:
            newsletter_emails.record_open(mid, recipient_email=recipient)
        except Exception:
            pass
    return _redirect(OPEN_TRACKING_LOGO_URL)


@router.get("/newsletter/click")
async def newsletter_click(request: Request) -> RedirectResponse:
    mid = (request.query_params.get("mid") or "").strip()
    recipient = _decode_b64(request.query_params.get("r"))
    target = _safe_redirect_url(_decode_b64(request.query_params.get("to")))
    if mid:
        try:
            newsletter_emails.record_click(mid, recipient_email=recipient, url=target)
        except Exception:
            pass
    return _redirect(target or CLICK_FALLBACK_URL)


@router.get("/email_agent/open.gif")
async def email_agent_open(request: Request) -> RedirectResponse:
    tid = (request.query_params.get("tid") or "").strip()
    if tid:
        try:
            email_agent_drafts.record_open(tid, recipient_email=None)
        except Exception:
            pass
    return _redirect(OPEN_TRACKING_LOGO_URL)


@router.get("/email_agent/click")
async def email_agent_click(request: Request) -> RedirectResponse:
    tid = (request.query_params.get("tid") or "").strip()
    recipient = _decode_b64(request.query_params.get("r"))
    target = _safe_redirect_url(_decode_b64(request.query_params.get("to")))
    if tid:
        try:
            email_agent_drafts.record_click(tid, recipient_email=recipient)
        except Exception:
            pass
    return _redirect(target or CLICK_FALLBACK_URL)
