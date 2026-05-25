"""EasyPost USPS rate calc — port of Rails `ShippingCalculatorService#calculate_via_easypost`.

Returns a list of `shipping_rate_data` dicts (same shape the controller formats for the shop),
sorted cheapest-first, USPS-only. Returns `[]` when there's no API key or on any error (the
caller renders the generic "unable to calculate" error, matching Rails). The `easypost` lib is
imported lazily so the rest of the server doesn't depend on it.
"""

from __future__ import annotations


def _fmt_address(addr: dict) -> dict:
    return {
        "street1": addr.get("line1") or addr.get("address_line"),
        "street2": addr.get("line2"),
        "city": addr.get("city"),
        "state": addr.get("state") or addr.get("subdivision"),
        "zip": addr.get("postal_code") or addr.get("zip"),
        "country": addr.get("country") or "US",
    }


def _estimate(service_name: str) -> dict:
    s = (service_name or "").lower()
    if "priority mail express" in s:
        mn, mx = 1, 2
    elif "priority mail" in s:
        mn, mx = 2, 3
    elif "first-class" in s or "first class" in s:
        mn, mx = 3, 5
    elif "parcel select" in s:
        mn, mx = 5, 7
    else:
        mn, mx = 3, 7
    return {
        "minimum": {"unit": "business_day", "value": mn},
        "maximum": {"unit": "business_day", "value": mx},
    }


def calculate_usps_rates(weight_oz: float, from_address: dict, to_address: dict,
                         api_key: str, currency: str = "usd") -> list[dict]:
    if not api_key or float(weight_oz) <= 0:
        return []
    try:
        import easypost

        client = easypost.EasyPostClient(api_key)
        shipment = client.shipment.create(
            to_address=_fmt_address(to_address),
            from_address=_fmt_address(from_address),
            parcel={"weight": weight_oz, "length": 10, "width": 10, "height": 10},
        )
        rates = getattr(shipment, "rates", None) or []
        usps = [r for r in rates if getattr(r, "carrier", None) == "USPS"]
        out = []
        for r in usps:
            value = float(getattr(r, "rate", 0) or getattr(r, "price", 0) or 0)
            service = getattr(r, "service", None) or "Standard"
            out.append({
                "shipping_rate_data": {
                    "type": "fixed_amount",
                    "fixed_amount": {"amount": round(value * 100), "currency": currency},
                    "display_name": f"{service} - USPS",
                    "delivery_estimate": _estimate(service),
                }
            })
        out.sort(key=lambda x: x["shipping_rate_data"]["fixed_amount"]["amount"])
        return out
    except Exception:
        return []
