"""CORS parity with Edgar's global rack-cors (any origin, all methods, no creds) — needed for
the agroverse.shop browser fetch to /agroverse_shop/shipping_rates (PR4)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app

client = TestClient(create_app())
ORIGIN = {"Origin": "https://www.agroverse.shop"}


def test_cors_header_on_simple_get():
    r = client.get("/healthz", headers=ORIGIN)
    assert r.headers.get("access-control-allow-origin") == "*"


def test_cors_preflight_for_shipping_rates():
    r = client.options(
        "/agroverse_shop/shipping_rates",
        headers={**ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
