"""Tests for /dao/transactions, /dao/qr-codes, /dao/inventory-movements.

All sheet reads are mocked — no network calls.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.sheets import (
    inventory_movements as im_module,
    qr_codes as qr_module,
    transactions as tx_module,
)

client = TestClient(create_app(), follow_redirects=False)

# ── Mock data ──────────────────────────────────────────────────────────────

_MOCK_TRANSACTIONS = [
    {"date": "20260115", "partner": "SOHA", "sku": "ceremonial-cacao-fazenda-santa-ana-2023-200g",
     "qty": 10, "qr_code": "", "value": 0, "status": "", "source_sheet": "QR Code Sales", "source_row": 2},
    {"date": "20260115", "partner": "SOHA", "sku": "oscar-bahia-ceremonial-cacao-200g",
     "qty": 10, "qr_code": "", "value": 0, "status": "", "source_sheet": "QR Code Sales", "source_row": 3},
    {"date": "20260301", "partner": "David Campbell", "sku": "ceremonial-cacao-fazenda-santa-ana-2023-200g",
     "qty": 5, "qr_code": "", "value": 0, "status": "", "source_sheet": "QR Code Sales", "source_row": 4},
]

_MOCK_QR_CODES = [
    {"qr_code": "2024OSCAR_20260121_12", "sku": "oscar-bahia-ceremonial-cacao-200g",
     "status": "MINTED", "manager": "Kirsten", "owner": "", "price": "25",
     "farm": "Oscar", "year": "2024", "ledger_name": "AGL#25", "source_sheet": "Agroverse QR codes", "source_row": 2},
    {"qr_code": "2024OSCAR_20260121_13", "sku": "oscar-bahia-ceremonial-cacao-200g",
     "status": "SOLD", "manager": "Kirsten", "owner": "buyer@example.com", "price": "25",
     "farm": "Oscar", "year": "2024", "ledger_name": "AGL#25", "source_sheet": "Agroverse QR codes", "source_row": 3},
    {"qr_code": "2024OSCAR_20260121_14", "sku": "ceremonial-cacao-fazenda-santa-ana-2023-200g",
     "status": "MINTED", "manager": "Gary", "owner": "", "price": "30",
     "farm": "Fazenda Santa Ana", "year": "2023", "ledger_name": "AGL#25", "source_sheet": "Agroverse QR codes", "source_row": 4},
]

_MOCK_INVENTORY_MOVEMENTS = [
    {"date": "20260315", "sender": "Kirsten", "recipient": "SOHA",
     "sku": "ceremonial-cacao-fazenda-santa-ana-2023-200g", "qty": 10,
     "ledger_name": "AGL#25", "status": "PROCESSED", "source_sheet": "Inventory Movement", "source_row": 2},
    {"date": "20260315", "sender": "Kirsten", "recipient": "SOHA",
     "sku": "oscar-bahia-ceremonial-cacao-200g", "qty": 10,
     "ledger_name": "AGL#25", "status": "PROCESSED", "source_sheet": "Inventory Movement", "source_row": 3},
    {"date": "20260401", "sender": "Gary", "recipient": "David Campbell",
     "sku": "ceremonial-cacao-fazenda-santa-ana-2023-200g", "qty": 5,
     "ledger_name": "AGL#25", "status": "PROCESSED", "source_sheet": "Inventory Movement", "source_row": 4},
]


# ── /dao/transactions ──────────────────────────────────────────────────────

def test_transactions_no_filters(monkeypatch):
    monkeypatch.setattr(tx_module, "query", lambda **k: _MOCK_TRANSACTIONS)
    r = client.get("/dao/transactions")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert data["results"][0]["partner"] == "SOHA"


def test_transactions_partner_filter(monkeypatch):
    def fake(**k):
        return [t for t in _MOCK_TRANSACTIONS if "soha" in t["partner"].lower()]
    monkeypatch.setattr(tx_module, "query", fake)
    r = client.get("/dao/transactions?partner=soha")
    assert r.status_code == 200
    assert all(t["partner"] == "SOHA" for t in r.json()["results"])


def test_transactions_sku_filter(monkeypatch):
    def fake(**k):
        return [t for t in _MOCK_TRANSACTIONS if "oscar" in t["sku"].lower()]
    monkeypatch.setattr(tx_module, "query", fake)
    r = client.get("/dao/transactions?sku=oscar")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert "oscar" in r.json()["results"][0]["sku"]


def test_transactions_empty_results(monkeypatch):
    monkeypatch.setattr(tx_module, "query", lambda **k: [])
    r = client.get("/dao/transactions?partner=nonexistent")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_transactions_limit(monkeypatch):
    monkeypatch.setattr(tx_module, "query", lambda **k: _MOCK_TRANSACTIONS[:k.get("limit", 100)])
    r = client.get("/dao/transactions?limit=1")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_transactions_limit_clamp(monkeypatch):
    # limit > 1000 should be rejected by FastAPI validation
    r = client.get("/dao/transactions?limit=2000")
    assert r.status_code == 422  # validation error


# ── /dao/qr-codes ──────────────────────────────────────────────────────────

def test_qr_codes_no_filters(monkeypatch):
    monkeypatch.setattr(qr_module, "query", lambda **k: _MOCK_QR_CODES)
    r = client.get("/dao/qr-codes")
    assert r.status_code == 200
    assert r.json()["count"] == 3


def test_qr_codes_manager_filter(monkeypatch):
    def fake(**k):
        mgr = (k.get("manager") or "").lower()
        return [q for q in _MOCK_QR_CODES if mgr in q["manager"].lower()]
    monkeypatch.setattr(qr_module, "query", fake)
    r = client.get("/dao/qr-codes?manager=kirsten")
    assert r.status_code == 200
    assert all(q["manager"] == "Kirsten" for q in r.json()["results"])


def test_qr_codes_status_filter(monkeypatch):
    def fake(**k):
        st = (k.get("status") or "").lower()
        return [q for q in _MOCK_QR_CODES if q["status"].lower() == st]
    monkeypatch.setattr(qr_module, "query", fake)
    r = client.get("/dao/qr-codes?status=SOLD")
    assert r.status_code == 200
    assert all(q["status"] == "SOLD" for q in r.json()["results"])


def test_qr_codes_sku_filter(monkeypatch):
    def fake(**k):
        sku = (k.get("sku") or "").lower()
        return [q for q in _MOCK_QR_CODES if sku in q["sku"].lower()]
    monkeypatch.setattr(qr_module, "query", fake)
    r = client.get("/dao/qr-codes?sku=santa-ana")
    assert r.status_code == 200
    assert r.json()["count"] == 1


# ── /dao/inventory-movements ───────────────────────────────────────────────

def test_inventory_movements_no_filters(monkeypatch):
    monkeypatch.setattr(im_module, "query", lambda **k: _MOCK_INVENTORY_MOVEMENTS)
    r = client.get("/dao/inventory-movements")
    assert r.status_code == 200
    assert r.json()["count"] == 3


def test_inventory_movements_person_filter(monkeypatch):
    def fake(**k):
        p = (k.get("person") or "").lower()
        role = k.get("role") or ""
        results = []
        for m in _MOCK_INVENTORY_MOVEMENTS:
            if role == "sender":
                if p in m["sender"].lower():
                    results.append(m)
            elif role == "recipient":
                if p in m["recipient"].lower():
                    results.append(m)
            else:
                if p in m["sender"].lower() or p in m["recipient"].lower():
                    results.append(m)
        return results
    monkeypatch.setattr(im_module, "query", fake)
    r = client.get("/dao/inventory-movements?person=campbell&role=recipient")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["results"][0]["recipient"] == "David Campbell"


def test_inventory_movements_sender_role(monkeypatch):
    def fake(**k):
        p = (k.get("person") or "").lower()
        return [m for m in _MOCK_INVENTORY_MOVEMENTS if p in m["sender"].lower()]
    monkeypatch.setattr(im_module, "query", fake)
    r = client.get("/dao/inventory-movements?person=kirsten&role=sender")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_inventory_movements_empty(monkeypatch):
    monkeypatch.setattr(im_module, "query", lambda **k: [])
    r = client.get("/dao/inventory-movements?person=nobody")
    assert r.status_code == 200
    assert r.json()["count"] == 0


# ── Error handling ─────────────────────────────────────────────────────────

def test_sheet_error_returns_empty_results(monkeypatch):
    monkeypatch.setattr(tx_module, "query", lambda **k: [{"error": "Failed to read sheet: API error"}])
    r = client.get("/dao/transactions")
    assert r.status_code == 200
    assert "error" in r.json()["results"][0]
