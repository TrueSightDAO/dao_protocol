"""Server-side empty-body / missing-signature guard for POST /dao/submit_contribution.

Covers the guard filed in agentic_ai_context/OPEN_FOLLOWUPS.md
("dao_protocol: server-side guard - reject empty body / missing signature format"):
an empty body (or the ``[No Text Provided]`` sentinel) and a signature-requiring
report form that arrives WITHOUT a signature block must be rejected with HTTP 400
instead of being recorded as a real ``no_signature_format`` event.

Sheets + verify are stubbed; no network, no Google access.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from truesight_dao_client.server import dispatch
from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.sheets import telegram_raw_log

client = TestClient(create_app())


def _stub_logging(monkeypatch):
    """Stub Sheets logging + background dispatch; return the captured calls."""
    calls = {"logged": [], "dispatched": []}
    monkeypatch.setattr(
        telegram_raw_log,
        "add_record",
        lambda text, **k: calls["logged"].append((text, k.get("signature_verification")))
        or True,
    )
    monkeypatch.setattr(dispatch, "dispatch_event", lambda text: calls["dispatched"].append(text))
    return calls


def test_empty_body_rejected(monkeypatch):
    calls = _stub_logging(monkeypatch)
    # No ``text`` field at all -> empty body.
    r = client.post("/dao/submit_contribution", data={})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_body"
    assert calls["logged"] == []          # nothing persisted
    assert calls["dispatched"] == []


def test_whitespace_only_body_rejected(monkeypatch):
    calls = _stub_logging(monkeypatch)
    r = client.post("/dao/submit_contribution", data={"text": "   \n  "})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_body"
    assert calls["logged"] == []


def test_no_text_provided_sentinel_rejected(monkeypatch):
    calls = _stub_logging(monkeypatch)
    r = client.post("/dao/submit_contribution", data={"text": "[No Text Provided]"})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_body"
    assert calls["logged"] == []


def test_unsigned_inventory_movement_rejected(monkeypatch):
    calls = _stub_logging(monkeypatch)
    r = client.post(
        "/dao/submit_contribution",
        data={"text": "[INVENTORY MOVEMENT]\n- QR Code: 2024OSCAR_20260121_12"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "missing_signature_format"
    assert calls["logged"] == []
    assert calls["dispatched"] == []


def test_unsigned_contribution_event_rejected(monkeypatch):
    calls = _stub_logging(monkeypatch)
    r = client.post(
        "/dao/submit_contribution",
        data={"text": "[CONTRIBUTION EVENT]\n- Type: Time (Minutes)\n- Amount: 30"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "missing_signature_format"
    assert calls["logged"] == []


def test_unsigned_non_signed_form_still_logs(monkeypatch):
    """Regression guard: a marker-less non-signed submission is still recorded."""
    calls = _stub_logging(monkeypatch)
    r = client.post("/dao/submit_contribution", data={"text": "just a note, no markers"})
    assert r.status_code == 200
    assert r.json()["signature_verification"] == "no_signature_format"
    assert len(calls["logged"]) == 1
    assert calls["dispatched"] == []


def test_unsigned_email_event_still_logs(monkeypatch):
    """Non-signed event types (email onboarding) must keep working."""
    calls = _stub_logging(monkeypatch)
    r = client.post(
        "/dao/submit_contribution",
        data={"text": "[EMAIL REGISTERED EVENT]\n- Email: alice@example.com"},
    )
    assert r.status_code == 200
    assert r.json()["signature_verification"] == "no_signature_format"
    assert len(calls["logged"]) == 1


def test_signed_contribution_event_still_accepted(monkeypatch):
    """A properly signed report form is unaffected by the guard."""
    calls = _stub_logging(monkeypatch)
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "public_key": "PUBKEY"})
    text = (
        "[CONTRIBUTION EVENT]\n- Type: Time (Minutes)\n- Amount: 30\n--------\n"
        "My Digital Signature: PUBKEY\nRequest Transaction ID: SIG=="
    )
    r = client.post("/dao/submit_contribution", data={"text": text})
    assert r.status_code == 200
    assert r.json()["signature_verification"] == "success"
    assert calls["dispatched"] == [text]
