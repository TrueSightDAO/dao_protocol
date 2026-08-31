"""Unit tests for the A4 public-ledger emit hook."""

import json


from truesight_dao_client.server.services import ledger_emit


class _S:
    github_ledger_repo = "TrueSightDAO/verify_public_signatures"
    github_ledger_pat = "fake-pat"
    github_pat = "fake-pat"


PLANTING_TEXT = """- Event: [TREE PLANTING EVENT]
- Latitude: 44.56
- Longitude: -123.26
--------
My Digital Signature: MIIB...SPKI
Request Transaction ID: TXN_HASH_123
"""


def _verification(payload=None):
    return {
        "success": True,
        "payload": payload or PLANTING_TEXT.split("--------")[0].strip(),
        "signature": "TXN_HASH_123",
        "public_key": "-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----",
    }


def test_folder_mapping(monkeypatch):
    assert ledger_emit._folder_for(PLANTING_TEXT) == "tree_planting"
    assert ledger_emit._folder_for("no event here") is None
    assert ledger_emit._folder_for("[EMAIL VERIFICATION] x@y.com") is None


def test_pii_scan():
    assert ledger_emit._has_pii("farmer@example.com") is False      # allowlisted
    assert ledger_emit._has_pii("farmer@gmail.com") is True         # real email
    assert ledger_emit._has_pii("no emails here") is False


def test_emit_skips_non_ledger_events():
    assert ledger_emit.emit("[EMAIL VERIFICATION] farmer@gmail.com", _verification(), "Edgar_1") is False
    assert ledger_emit.emit("just a note", _verification(), "Edgar_2") is False


def test_emit_skips_pii(monkeypatch):
    called = []
    monkeypatch.setattr(ledger_emit, "get_settings", lambda: _S())
    monkeypatch.setattr(ledger_emit, "_put_file",
                        lambda pat, repo, path, content: called.append((pat, repo, path, content)) or True)
    text = "- Event: [TREE PLANTING EVENT]\n- Email: farmer@gmail.com\n--------\nMy Digital Signature: X\nRequest Transaction ID: Y"
    assert ledger_emit.emit(text, _verification(), "Edgar_3") is False
    assert called == []


def test_emit_writes_verified_event(monkeypatch):
    called = []
    monkeypatch.setattr(ledger_emit, "get_settings", lambda: _S())
    monkeypatch.setattr(ledger_emit, "_put_file",
                        lambda pat, repo, path, content: called.append((pat, repo, path, content)) or True)
    monkeypatch.setattr(ledger_emit, "_resolve_contributor", lambda pk: "Gary Teh")
    assert ledger_emit.emit(PLANTING_TEXT, _verification(), "171") is True
    assert len(called) == 1
    pat, repo, path, content = called[0]
    assert repo == "TrueSightDAO/verify_public_signatures"
    assert path == "tree_planting/171.json"
    assert content["telegram_message_id"] == "171"
    assert content["event_type"] == "[TREE PLANTING EVENT]"
    assert content["contributor_name"] == "Gary Teh"
    assert content["verifiable"] is True
    assert content["signed_payload"]  # exact bytes signed
    json.dumps(content)  # serializable
