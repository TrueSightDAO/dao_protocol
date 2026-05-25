"""Agroverse Shop checkout shipping estimates — port of Rails
`AgroverseShopShippingRatesController#show` (PR4).

`GET /agroverse_shop/shipping_rates?weightOz=<float>&shippingAddress=<json>&environment=<env>`
→ EasyPost USPS rates, formatted for the shop. Read-only (no writes), so safe to shadow vs Rails.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..services import easypost as easypost_service

router = APIRouter()

# Origin = META_CHECKOUT_ORIGIN_* prod defaults (warehouse ship-from; not secret).
ORIGIN_ADDRESS = {
    "line1": "1423 Hayes St",
    "city": "San Francisco",
    "state": "CA",
    "postal_code": "94117",
    "country": "US",
}
# Same default destination as the GAS/Rails path when no address is supplied.
DEFAULT_DESTINATION = {
    "line1": "1600 Pennsylvania Avenue NW",
    "city": "Washington",
    "state": "DC",
    "postal_code": "20500",
    "country": "US",
}


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_shipping_address(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _destination(shipping_address: dict | None) -> dict:
    if shipping_address and shipping_address.get("address"):
        return {k: v for k, v in {
            "line1": str(shipping_address.get("address") or ""),
            "line2": shipping_address.get("line2"),
            "city": str(shipping_address.get("city") or ""),
            "state": str(shipping_address.get("state") or ""),
            "postal_code": str(shipping_address.get("zip") or ""),
            "country": shipping_address.get("country") or "US",
        }.items() if v not in (None, "")}
    return dict(DEFAULT_DESTINATION)


def _format_rates(options: list[dict]) -> list[dict]:
    formatted = []
    for j, rate in enumerate(options):
        sr = rate.get("shipping_rate_data", {})
        amount_cents = (sr.get("fixed_amount") or {}).get("amount") or 0
        est = sr.get("delivery_estimate") or {}
        mn = (est.get("minimum") or {}).get("value", 3)
        mx = (est.get("maximum") or {}).get("value", 7)
        formatted.append({
            "id": f"rate_{j}",
            "name": sr.get("display_name") or "Shipping",
            "amount": round(amount_cents / 100.0, 2),
            "amountCents": amount_cents,
            "deliveryDays": f"{mn}-{mx} business days",
        })
    return formatted


@router.get("/agroverse_shop/shipping_rates")
async def shipping_rates(request: Request) -> JSONResponse:
    weight_oz = _to_float(request.query_params.get("weightOz"))
    if weight_oz <= 0:
        return JSONResponse({
            "status": "error",
            "error": "weightOz parameter is required and must be greater than 0",
        })

    to_address = _destination(_parse_shipping_address(request.query_params.get("shippingAddress")))
    options = easypost_service.calculate_usps_rates(
        weight_oz=weight_oz,
        from_address=ORIGIN_ADDRESS,
        to_address=to_address,
        api_key=get_settings().easypost_api_key,
    )

    if not options:
        return JSONResponse({
            "status": "error",
            "error": "Unable to calculate shipping rates. Please ensure EasyPost API is "
                     "configured and address is valid. Check server logs for details.",
        })

    return JSONResponse({
        "status": "success",
        "rates": _format_rates(options),
        "totalWeightOz": weight_oz,
    })
