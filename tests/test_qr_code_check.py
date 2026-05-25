"""Tests for /qr-code-check (PR6a). Lookup, Stripe, and sheet writes are mocked — no network."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import qr_code_check as route
from truesight_dao_client.server.sheets import qr_code_lookup, qr_code_sales
from truesight_dao_client.server.services import stripe_client

client = TestClient(create_app(), follow_redirects=False)

_MINTED = {"qr_code": "QR1", "status": "MINTED", "landing_page": "https://agroverse.shop/p/qr1",
           "Currency": "Ceremonial Cacao", "Price": "25", "farm name": "Oscar", "state": "Bahia",
           "country": "Brazil", "Year": "2024", "Product Image": "https://img/x.jpg"}
_SAMPLE = {**_MINTED, "status": "SAMPLE"}


def test_missing_qr_code_400():
    assert client.get("/qr-code-check").status_code == 400


def test_format_json_returns_lookup(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: {"qr_code": c, "status": "MINTED", "landing_page": "x"})
    r = client.get("/qr-code-check?qr_code=QR1&format=json")
    assert r.status_code == 200 and r.json()["status"] == "MINTED"


def test_error_lookup_returns_json(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: {"error": "not found", "qr_code": c})
    assert client.get("/qr-code-check?qr_code=NOPE").json()["error"] == "not found"


def test_sample_redirects_to_landing(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _SAMPLE)
    r = client.get("/qr-code-check?qr_code=QR1")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://agroverse.shop/p/qr1?")
    assert "utm_campaign=sample_gift" in loc and "status=SAMPLE" in loc


def test_minted_creates_session_and_redirects(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _MINTED)
    captured = {}
    def fake_create(qr, product_data, cents, success_url, cancel_url):
        captured.update(cents=cents, name=product_data["name"], success=success_url)
        return SimpleNamespace(url="https://checkout.stripe.com/pay")
    monkeypatch.setattr(stripe_client, "create_qr_checkout_session", fake_create)
    r = client.get("/qr-code-check?qr_code=QR1")
    assert r.status_code == 302
    assert r.headers["location"] == "https://checkout.stripe.com/pay"
    assert captured["cents"] == 2500
    assert "session_id={CHECKOUT_SESSION_ID}" in captured["success"]


def test_minted_no_stripe_is_502(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _MINTED)
    monkeypatch.setattr(stripe_client, "create_qr_checkout_session", lambda *a, **k: None)
    assert client.get("/qr-code-check?qr_code=QR1").status_code == 502


def _paid_session(qr="QR1"):
    charge = SimpleNamespace(amount=2500, balance_transaction="bt_1")
    return SimpleNamespace(
        payment_status="paid", metadata={"qr_code": qr},
        payment_intent=SimpleNamespace(charges=SimpleNamespace(data=[charge])),
        customer_details={"email": "buyer@example.com"}, customer_email=None, created=1700000000,
    )


def test_session_reconcile_marks_sold(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _MINTED)
    monkeypatch.setattr(stripe_client, "retrieve_session_with_charges", lambda sid: _paid_session())
    monkeypatch.setattr(stripe_client, "retrieve_balance_transaction", lambda bt: SimpleNamespace(fee=30))
    monkeypatch.setattr(qr_code_sales, "already_recorded", lambda c: False)
    rec = {}
    monkeypatch.setattr(qr_code_sales, "mark_sold_and_record",
                        lambda *a, **k: rec.update(args=a) or {"ok": True})
    r = client.get("/qr-code-check?qr_code=QR1&session_id=cs_test_1")
    assert r.status_code == 302
    assert "status=SOLD" in r.headers["location"]
    # net = (2500-30)/100 = 24.7, fee=0.3, total=25.0 → passed positionally
    assert rec["args"][2] == 24.7 and rec["args"][4] == 25.0


def test_session_unpaid_is_400(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _MINTED)
    s = _paid_session(); s.payment_status = "unpaid"
    monkeypatch.setattr(stripe_client, "retrieve_session_with_charges", lambda sid: s)
    assert client.get("/qr-code-check?qr_code=QR1&session_id=cs_x").status_code == 400


def test_session_already_recorded_is_400(monkeypatch):
    monkeypatch.setattr(qr_code_lookup, "lookup", lambda c: _MINTED)
    monkeypatch.setattr(stripe_client, "retrieve_session_with_charges", lambda sid: _paid_session())
    monkeypatch.setattr(qr_code_sales, "already_recorded", lambda c: True)
    r = client.get("/qr-code-check?qr_code=QR1&session_id=cs_x")
    assert r.status_code == 400 and "already recorded" in r.json()["error"]
