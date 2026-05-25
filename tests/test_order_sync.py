"""Tests for the order-sync audit-log (PR6b). Stripe + checkout-log mocked — no network."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from truesight_dao_client.server import order_sync
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.services import stripe_client
from truesight_dao_client.server.sheets import stripe_checkout_log

client = TestClient(create_app())


def _session(metadata, *, amount_total=5000, currency="usd", livemode=True, item_desc="[TBM] — Donation"):
    line_items = SimpleNamespace(data=[SimpleNamespace(description=item_desc, price=None)])
    charge = SimpleNamespace(amount=amount_total, balance_transaction="bt_1")
    return SimpleNamespace(
        id="cs_live_1", metadata=metadata, amount_total=amount_total, currency=currency,
        livemode=livemode, line_items=line_items, customer_details={"name": "Donor"},
        payment_intent=SimpleNamespace(charges=SimpleNamespace(data=[charge])),
    )


def test_ledger_tagged_creates_record(monkeypatch):
    monkeypatch.setattr(stripe_client, "retrieve_session_full", lambda sid: _session({"ledger": "TBM"}))
    monkeypatch.setattr(stripe_client, "retrieve_balance_transaction", lambda bt: SimpleNamespace(fee=175))
    monkeypatch.setattr(stripe_checkout_log, "record_exists", lambda sid: False)
    captured = {}
    monkeypatch.setattr(stripe_checkout_log, "append_record", lambda **k: captured.update(k) or True)
    assert order_sync.sync("cs_live_1") == {"status": "created"}
    assert captured["items"] == "[TBM] — Donation"
    assert captured["amount"] == 50.0
    assert captured["environment"] == "PRODUCTION"
    assert captured["stripe_fee_cents"] == 175


def test_meta_channel_skipped(monkeypatch):
    monkeypatch.setattr(stripe_client, "retrieve_session_full",
                        lambda sid: _session({"channel": "meta", "wix_products": "p:1"}))
    assert order_sync.sync("cs_x")["status"] == "skipped"


def test_untagged_skipped(monkeypatch):
    monkeypatch.setattr(stripe_client, "retrieve_session_full", lambda sid: _session({}))
    assert order_sync.sync("cs_x")["status"] == "skipped"


def test_duplicate_already_exists(monkeypatch):
    monkeypatch.setattr(stripe_client, "retrieve_session_full", lambda sid: _session({"ledger": "AGL15"}))
    monkeypatch.setattr(stripe_checkout_log, "record_exists", lambda sid: True)
    assert order_sync.sync("cs_x") == {"status": "already_exists"}


def test_route_requires_session_id():
    assert client.post("/stripe/order_sync").status_code == 400


def test_route_delegates(monkeypatch):
    monkeypatch.setattr(order_sync, "sync", lambda sid: {"status": "created", "sid": sid})
    r = client.post("/stripe/order_sync?session_id=cs_abc")
    assert r.status_code == 200 and r.json() == {"status": "created", "sid": "cs_abc"}
