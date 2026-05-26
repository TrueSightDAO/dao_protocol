"""Tests for email onboarding (EMAIL REGISTERED / VERIFICATION). Sheet ops + GAS mailer mocked."""

from __future__ import annotations

from fastapi.testclient import TestClient

from truesight_dao_client.server import dedup, email_registration as er
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import dao
from truesight_dao_client.server.sheets import contributors_digital_signatures as cds
from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.sheets import telegram_raw_log

client = TestClient(create_app())

VR = {"success": True, "public_key": "PUBKEY_PEM"}
REG = "[EMAIL REGISTERED EVENT]\n- Email: Alice@Example.com\n--------\nMy Digital Signature: PUBKEY_PEM\nRequest Transaction ID: SIG=="
VER = "[EMAIL VERIFICATION EVENT]\n- Email: alice@example.com\n- Verification Key: VK123\n--------\nMy Digital Signature: PUBKEY_PEM\nRequest Transaction ID: SIG=="


def test_not_applicable_without_success():
    assert er.handle_after_successful_verify(REG, {"success": False}) == {"applicable": False}


def test_not_applicable_non_email_event():
    assert er.handle_after_successful_verify("[SALES EVENT]\n--------\n", VR) == {"applicable": False}


def test_registration_new_sends_email(monkeypatch):
    monkeypatch.setattr(cds, "normalize_public_key", lambda v: "PK1")
    monkeypatch.setattr(cds, "find_by_public_key", lambda pk: None)
    captured = {}
    monkeypatch.setattr(cds, "append_pending_row", lambda e, p, vk: captured.update(email=e, pk=p) or True)
    monkeypatch.setattr(er, "_trigger_verification_email", lambda email, vk, ru: {"ok": True})
    out = er.handle_after_successful_verify(REG, VR)
    assert out["applicable"] and out["ok"] and out["verification_email_sent"]
    assert captured["email"] == "alice@example.com"        # extracted + lowercased


def test_registration_existing_is_skipped(monkeypatch):
    monkeypatch.setattr(cds, "normalize_public_key", lambda v: "PK1")
    monkeypatch.setattr(cds, "find_by_public_key", lambda pk: {"status": "ACTIVE", "email": "alice@example.com", "row": 5})
    out = er.handle_after_successful_verify(REG, VR)
    assert out["ok"] and out["skipped"] and out["verification_email_sent"] is False


def test_registration_missing_email_fails(monkeypatch):
    monkeypatch.setattr(cds, "normalize_public_key", lambda v: "PK1")
    bad = "[EMAIL REGISTERED EVENT]\n--------\nMy Digital Signature: PUBKEY_PEM\nRequest Transaction ID: S"
    out = er.handle_after_successful_verify(bad, VR)
    assert out["ok"] is False and "email" in out["error"].lower()


def test_verification_activated(monkeypatch):
    monkeypatch.setattr(cds, "normalize_public_key", lambda v: "PK1")
    monkeypatch.setattr(cds, "normalize_verification_key", lambda v: "VK123")
    monkeypatch.setattr(cds, "consume_verification", lambda pk, vk, email=None: {"outcome": "activated", "row": 9})
    out = er.handle_after_successful_verify(VER, VR)
    assert out["ok"] and out["activated"] is True


def test_verification_pubkey_mismatch(monkeypatch):
    monkeypatch.setattr(cds, "normalize_public_key", lambda v: "PK1")
    monkeypatch.setattr(cds, "normalize_verification_key", lambda v: "VK123")
    monkeypatch.setattr(cds, "consume_verification", lambda pk, vk, email=None: {"outcome": "pubkey_mismatch", "row": 9})
    out = er.handle_after_successful_verify(VER, VR)
    assert out["ok"] is False and "different device" in out["error"]


def test_dao_route_returns_422_on_email_failure(monkeypatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "public_key": "PUBKEY_PEM"})
    monkeypatch.setattr(dedup, "is_duplicate", lambda sig: False)
    monkeypatch.setattr(telegram_raw_log, "add_record", lambda *a, **k: True)
    monkeypatch.setattr(dao.email_registration, "handle_after_successful_verify",
                        lambda text, vr: {"applicable": True, "ok": False, "event": "EMAIL_REGISTERED", "error": "boom"})
    r = client.post("/dao/submit_contribution", data={"text": REG})
    assert r.status_code == 422
    assert r.json()["error"] == "boom"
