"""`POST /stripe/order_sync?session_id=…` — the delegation target for Rails' shared
`/stripe_webhook` `checkout.session.completed` handler (PR6b). Runs the order-sync audit-log
(ledger-tagged path); meta/Wix stays on Rails. The webhook ENTRY remains on Rails (it also routes
trading-SaaS subscription events), so this is invoked by Rails, not a public Stripe webhook.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import order_sync

router = APIRouter()


@router.post("/stripe/order_sync")
async def stripe_order_sync(request: Request) -> JSONResponse:
    session_id = (request.query_params.get("session_id") or "").strip()
    if not session_id:
        try:
            form = await request.form()
            session_id = str(form.get("session_id") or "").strip()
        except Exception:
            session_id = ""
    if not session_id:
        return JSONResponse({"status": "error", "error": "session_id required"}, status_code=400)
    try:
        return JSONResponse(order_sync.sync(session_id))
    except Exception as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
