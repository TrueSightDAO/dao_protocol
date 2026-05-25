"""Tests for /agroverse_shop/shipping_rates (PR4). EasyPost service mocked — no network."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import shipping

client = TestClient(create_app())

_CANNED = [{
    "shipping_rate_data": {
        "type": "fixed_amount",
        "fixed_amount": {"amount": 850, "currency": "usd"},
        "display_name": "Priority Mail - USPS",
        "delivery_estimate": {"minimum": {"value": 2}, "maximum": {"value": 3}},
    }
}]


def test_missing_weight_is_error():
    r = client.get("/agroverse_shop/shipping_rates")
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert "weightOz" in r.json()["error"]


def test_success_formats_rates_for_shop(monkeypatch):
    monkeypatch.setattr(shipping.easypost_service, "calculate_usps_rates", lambda **k: _CANNED)
    r = client.get("/agroverse_shop/shipping_rates?weightOz=8")
    body = r.json()
    assert body["status"] == "success"
    assert body["totalWeightOz"] == 8.0
    rate = body["rates"][0]
    assert rate == {
        "id": "rate_0",
        "name": "Priority Mail - USPS",
        "amount": 8.5,
        "amountCents": 850,
        "deliveryDays": "2-3 business days",
    }


def test_empty_rates_is_error(monkeypatch):
    monkeypatch.setattr(shipping.easypost_service, "calculate_usps_rates", lambda **k: [])
    r = client.get("/agroverse_shop/shipping_rates?weightOz=8")
    assert r.json()["status"] == "error"
    assert "Unable to calculate" in r.json()["error"]


def test_shipping_address_json_drives_destination(monkeypatch):
    captured = {}
    monkeypatch.setattr(shipping.easypost_service, "calculate_usps_rates",
                        lambda **k: captured.update(k) or _CANNED)
    addr = {"address": "742 Evergreen Terrace", "city": "Springfield", "state": "OR", "zip": "97477"}
    client.get(f"/agroverse_shop/shipping_rates?weightOz=12&shippingAddress={json.dumps(addr)}")
    assert captured["to_address"]["line1"] == "742 Evergreen Terrace"
    assert captured["to_address"]["postal_code"] == "97477"
    assert captured["from_address"]["postal_code"] == "94117"  # origin = SF warehouse


def test_malformed_address_falls_back_to_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(shipping.easypost_service, "calculate_usps_rates",
                        lambda **k: captured.update(k) or _CANNED)
    client.get("/agroverse_shop/shipping_rates?weightOz=5&shippingAddress=not-json{{")
    assert captured["to_address"]["city"] == "Washington"  # default destination
