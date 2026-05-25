"""Tests for POST /dao/submit_contribution (PR5b/PR5c). verify/sheets/dedup/dispatch mocked."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from truesight_dao_client.server import dedup, dispatch
from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.sheets import telegram_raw_log

client = TestClient(create_app())

SIGNED = (
    "[SALES EVENT]\nItem: QR123\n--------\n"
    "My Digital Signature: PUBKEY\nRequest Transaction ID: SIG123=="
)


@pytest.fixture(autouse=True)
def _stub_sheets_and_dispatch(monkeypatch):
    calls = {"logged": [], "dispatched": []}
    monkeypatch.setattr(telegram_raw_log, "add_record",
                        lambda text, **k: calls["logged"].append((text, k.get("signature_verification"))) or True)
    monkeypatch.setattr(dispatch, "dispatch_event", lambda text: calls["dispatched"].append(text))
    monkeypatch.setattr(dedup, "is_duplicate", lambda sig: False)
    return calls


def test_get_not_allowed():
    assert client.get("/dao/submit_contribution").status_code == 405


def test_no_signature_format_logs_no_dispatch(_stub_sheets_and_dispatch):
    r = client.post("/dao/submit_contribution", data={"text": "just a note, no markers"})
    assert r.status_code == 200
    assert r.json()["signature_verification"] == "no_signature_format"
    assert len(_stub_sheets_and_dispatch["logged"]) == 1          # always logs
    assert _stub_sheets_and_dispatch["dispatched"] == []          # no dispatch


def test_valid_signature_logs_and_dispatches(monkeypatch, _stub_sheets_and_dispatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "message": "ok"})
    r = client.post("/dao/submit_contribution", data={"text": SIGNED})
    assert r.status_code == 200
    body = r.json()
    assert body["signature_verification"] == "success"
    assert body["googleSheetLogged"] is True
    assert _stub_sheets_and_dispatch["logged"][0][1] == "success"
    assert _stub_sheets_and_dispatch["dispatched"] == [SIGNED]    # dispatched on success


def test_failed_signature_logs_no_dispatch(monkeypatch, _stub_sheets_and_dispatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": False, "message": "bad"})
    r = client.post("/dao/submit_contribution", data={"text": SIGNED})
    assert r.json()["signature_verification"] == "failed"
    assert _stub_sheets_and_dispatch["dispatched"] == []


def test_duplicate_is_409(monkeypatch, _stub_sheets_and_dispatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True})
    monkeypatch.setattr(dedup, "is_duplicate", lambda sig: True)
    r = client.post("/dao/submit_contribution", data={"text": SIGNED})
    assert r.status_code == 409
    assert "Duplicate" in r.json()["error"]


def test_verify_error_is_recorded(monkeypatch, _stub_sheets_and_dispatch):
    def boom(t):
        raise verify.VerificationError("bad key")
    monkeypatch.setattr(verify, "verify", boom)
    r = client.post("/dao/submit_contribution", data={"text": SIGNED})
    assert r.json()["signature_verification"] == "error"
    assert _stub_sheets_and_dispatch["dispatched"] == []
