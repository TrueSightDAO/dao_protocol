"""Consumer product-QR scan → Stripe — port of Rails `qr_code_check_controller` (PR6a).

GET /qr-code-check?qr_code=…[&session_id=…][&format=json]
  - lookup the QR row; JSON for ?format=json / error / no landing_page
  - ?session_id present  → reconcile a returned Stripe Checkout (verify paid + qr match → mark SOLD
    + append QR Code Sales) then redirect to landing
  - status MINTED        → create a Stripe Checkout session, redirect to it
  - otherwise (SAMPLE/GIFT/SOLD/…) → redirect to landing with UTM
GET /link-email?qr_code=…&email=…  → write the buyer email onto the QR row (col L)

See STRIPE_LEDGER_ROUTING.md Flow 5. Live sale-reconcile testing is operator-driven (real Stripe).
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import get_settings
from ..sheets import base, qr_code_lookup, qr_code_sales
from ..services import stripe_client

router = APIRouter()
logger = logging.getLogger("dao_protocol.qr_code_check")
SAMPLE_GIFT_STATUSES = {"SAMPLE", "GIFT"}


def _utm_campaign(status: str) -> str:
    if not status:
        return "unknown"
    return "sample_gift" if status.upper() in SAMPLE_GIFT_STATUSES else status


def _slugify(product: str) -> str:
    if not product:
        return ""
    slug = re.sub(r"_+\Z", "", re.sub(r"\A_+", "", re.sub(r"[^a-z0-9]+", "_", product.lower())))
    return slug[:80]


def _redirect_with_utm(dest: str, qr_code: str, product: str, status: str) -> RedirectResponse:
    query = {"product": product, "qr_code": qr_code}
    if status:
        query["status"] = status
    query.update({
        "utm_source": "edgar", "utm_medium": "qr", "utm_campaign": _utm_campaign(status or ""),
        "utm_content": qr_code, "utm_term": _slugify(product or ""),
    })
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(dest + sep + urllib.parse.urlencode(query), status_code=302)


@router.get("/qr-code-check")
async def index(request: Request) -> object:
    qp = request.query_params
    qr_code = (qp.get("qr_code") or "").strip()
    if not qr_code:
        base_url = str(request.base_url).rstrip("/") + request.url.path
        return JSONResponse({
            "error": "Missing qr_code parameter",
            "instructions": f"Send a GET request with the qr_code query parameter. Example: {base_url}?qr_code=ABC123",
        }, status_code=400)

    result = qr_code_lookup.lookup(qr_code)
    if qp.get("format", "").lower() == "json":
        return JSONResponse(result)
    if result.get("error") or not result.get("landing_page"):
        return JSONResponse(result)

    session_id = qp.get("session_id")
    if session_id:
        return _reconcile(qr_code, session_id, result)

    if str(result.get("status")) == "MINTED":
        return _start_checkout(request, qr_code, result)

    return _redirect_with_utm(result["landing_page"], qr_code,
                              result.get("Currency") or "Product", str(result.get("status") or ""))


def _start_checkout(request: Request, qr_code: str, result: dict) -> object:
    origin_parts = [result.get(k) for k in ("farm name", "state", "country") if result.get(k)]
    origin = ", ".join(str(p) for p in origin_parts)
    currency = result.get("Currency") or "Product"
    description = (f"{currency}" + (f" from {origin}" if origin else "")
                  + (f", {result.get('Year')}" if result.get("Year") else "")
                  + ". Supports small-scale farmers and biodiversity. Complete your purchase to "
                    "plant a tree and restore the Amazon rainforest!")
    product_data = {"name": currency if currency != "Product" else f"Product (QR: {qr_code})",
                    "description": description,
                    "metadata": {"qr_code": qr_code, "product": currency,
                                 "farm_name": result.get("farm name") or "Unknown",
                                 "state": result.get("state") or "Unknown",
                                 "country": result.get("country") or "Unknown",
                                 "year": result.get("Year") or "Unknown"}}
    image = str(result.get("Product Image") or "").strip()
    if image:
        product_data["images"] = [image]

    base_url = str(request.base_url).rstrip("/") + request.url.path
    cancel = (_redirect_with_utm(result["landing_page"], qr_code, currency,
                                 str(result.get("status") or "")).headers["location"])
    try:
        unit_amount = int(float(result.get("Price") or 0)) * 100
        session = stripe_client.create_qr_checkout_session(
            qr_code, product_data, unit_amount,
            success_url=f"{base_url}?qr_code={qr_code}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=cancel,
        )
    except Exception as exc:
        logger.warning("stripe session create failed for %s: %s", qr_code, exc)
        session = None
    if session is None:
        return JSONResponse({"error": "Stripe not configured or checkout creation failed"}, status_code=502)
    return RedirectResponse(session.url, status_code=302)


def _reconcile(qr_code: str, session_id: str, result: dict) -> object:
    try:
        session = stripe_client.retrieve_session_with_charges(session_id)
    except Exception as exc:
        return JSONResponse({"error": f"Stripe error: {exc}"}, status_code=400)
    if session is None:
        return JSONResponse({"error": "Stripe not configured"}, status_code=502)

    paid = getattr(session, "payment_status", None) == "paid"
    meta_qr = (getattr(session, "metadata", None) or {}).get("qr_code")
    if not (paid and meta_qr == qr_code):
        return JSONResponse({"error": "Invalid or unpaid Stripe session"}, status_code=400)

    if qr_code_sales.already_recorded(qr_code):
        return JSONResponse({"error": f"QR code {qr_code} already recorded in QR Code Sales"}, status_code=400)

    try:
        charge = session.payment_intent.charges.data[0]
        bt = charge.balance_transaction
        if isinstance(bt, str):
            bt = stripe_client.retrieve_balance_transaction(bt)
        total = charge.amount / 100.0
        fee = bt.fee / 100.0
        net = (charge.amount - bt.fee) / 100.0
        buyer = (getattr(session, "customer_details", None) or {}).get("email") or getattr(session, "customer_email", None) or ""
        sales_date = datetime.fromtimestamp(session.created, tz=timezone.utc).strftime("%Y%m%d")
    except Exception as exc:
        return JSONResponse({"error": f"Unable to read charge/balance transaction: {exc}"}, status_code=400)

    rec = qr_code_sales.mark_sold_and_record(qr_code, buyer, net, fee, total,
                                             result.get("Currency") or "Unknown", session_id, sales_date)
    if not rec.get("ok"):
        return JSONResponse({"error": rec.get("error", "Failed to record sale")}, status_code=400)
    logger.info("qr sale recorded: %s (inventory-snapshot enqueue pending)", qr_code)
    return _redirect_with_utm(result["landing_page"], qr_code, result.get("Currency") or "Product", "SOLD")


@router.get("/link-email")
async def register_email(request: Request) -> JSONResponse:
    qp = request.query_params
    qr_code = (qp.get("qr_code") or "").strip()
    email = (qp.get("email") or "").strip()
    if not qr_code:
        return JSONResponse({"status": "error", "message": "qr_code required"}, status_code=400)
    key = get_settings().google_sa_json_qr_sales
    try:
        row = base.find_row_by_col_a(qr_code_sales.AGROVERSE_QR_SS, qr_code_sales.AGROVERSE_QR_SHEET, qr_code, key_path=key)
        if not row:
            return JSONResponse({"status": "error", "message": "QR code not found"}, status_code=404)
        base.update_cell(qr_code_sales.AGROVERSE_QR_SS,
                         f"{base.quoted_prefix(qr_code_sales.AGROVERSE_QR_SHEET)}!L{row}", email, key_path=key)
        return JSONResponse({"status": "success", "message": "Email registered successfully",
                             "qr_code": qr_code, "email": email})
    except Exception as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
