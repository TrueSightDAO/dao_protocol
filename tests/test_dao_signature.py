"""Tests for the PR8a signature endpoints:
  - POST /dao/verify-signature       (port of Rails dao#verify_signature)
  - GET  /dao/check_digital_signature (port of Rails dao#check_digital_signature)

verify + the contributors-signatures sheet adapter are mocked (no live Sheets/RSA)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.sheets import contributors_digital_signatures as sigs

client = TestClient(create_app())


# ---- POST /dao/verify-signature ------------------------------------------------

def test_verify_signature_valid(monkeypatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True})
    r = client.post("/dao/verify-signature", data={"input_text": "signed blob"})
    assert r.status_code == 200
    assert r.json() == {"valid": True, "message": "Signature verification successful"}


def test_verify_signature_invalid_is_still_200(monkeypatch):
    # A parseable-but-not-matching signature → valid:false, 200 (matches Rails).
    monkeypatch.setattr(verify, "verify", lambda t: {"success": False})
    r = client.post("/dao/verify-signature", data={"input_text": "signed blob"})
    assert r.status_code == 200
    assert r.json()["valid"] is False


def test_verify_signature_bad_input_is_422(monkeypatch):
    def boom(t):
        raise verify.VerificationError("no signature found")
    monkeypatch.setattr(verify, "verify", boom)
    r = client.post("/dao/verify-signature", data={"input_text": "garbage"})
    assert r.status_code == 422
    assert r.json()["valid"] is False
    assert "no signature" in r.json()["error"]


def test_verify_signature_accepts_json_body(monkeypatch):
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True})
    r = client.post("/dao/verify-signature", json={"input_text": "signed blob"})
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_verify_signature_get_not_allowed():
    assert client.get("/dao/verify-signature").status_code == 405


# ---- GET /dao/check_digital_signature ------------------------------------------

def test_check_digital_signature_missing_param():
    r = client.get("/dao/check_digital_signature")
    assert r.status_code == 400
    assert r.json()["error"] == "signature is required"
    assert r.headers.get("access-control-allow-origin") == "*"


def test_check_digital_signature_active(monkeypatch):
    monkeypatch.setattr(sigs, "find_by_public_key",
                        lambda pk: {"row": 5, "status": "ACTIVE",
                                    "name": "Gary Teh", "email": "gary@example.com"})
    r = client.get("/dao/check_digital_signature", params={"signature": "PUBKEY"})
    assert r.status_code == 200
    assert r.json() == {"registered": True,
                        "contributor_name": "Gary Teh",
                        "contributor_email": "gary@example.com"}
    assert r.headers.get("access-control-allow-origin") == "*"


def test_check_digital_signature_verifying(monkeypatch):
    monkeypatch.setattr(sigs, "find_by_public_key",
                        lambda pk: {"row": 9, "status": "VERIFYING",
                                    "name": "Pending Person", "email": "pending@example.com"})
    r = client.get("/dao/check_digital_signature", params={"signature": "PUBKEY"})
    assert r.status_code == 200
    assert r.json() == {"registered": False,
                        "pending_verification": True,
                        "contributor_email": "pending@example.com"}


def test_check_digital_signature_not_found(monkeypatch):
    monkeypatch.setattr(sigs, "find_by_public_key", lambda pk: None)
    r = client.get("/dao/check_digital_signature", params={"signature": "PUBKEY"})
    assert r.status_code == 404
    assert r.json()["registered"] is False


def test_check_digital_signature_error_is_500(monkeypatch):
    def boom(pk):
        raise RuntimeError("sheets down")
    monkeypatch.setattr(sigs, "find_by_public_key", boom)
    r = client.get("/dao/check_digital_signature", params={"signature": "PUBKEY"})
    assert r.status_code == 500
    assert r.json()["registered"] is False
    assert "sheets down" in r.json()["error"]
