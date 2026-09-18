"""Regression tests for the 2026-09-18 "silent intake drop".

Before the fix, `telegram_raw_log.add_record` wrapped the Sheets append in
`except Exception: return ""` with no logging, and `/dao/submit_contribution`
returned `200 {"status":"ok"}` regardless. A transient Sheets failure therefore
produced a submission that was accepted to the submitter but never recorded.

These tests pin the three required behaviours:
  1. unconfirmed append  -> AppendFailure (loud), never a silent ""
  2. committed-but-lost-confirmation -> success (retry-safety: no duplicate row)
  3. the HTTP route surfaces (1) as a non-2xx instead of 200
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from truesight_dao_client.server import dispatch
from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.sheets import base, telegram_raw_log

client = TestClient(create_app())


def test_unconfirmed_append_raises_not_silently_drops(monkeypatch):
    """Sheets append blows up AND the row is absent -> raise, do not return ''."""

    def boom(*a, **k):
        raise RuntimeError("503 backend error")

    monkeypatch.setattr(base, "append_row", boom)
    monkeypatch.setattr(telegram_raw_log, "_row_present", lambda mid: False)

    with pytest.raises(telegram_raw_log.AppendFailure):
        telegram_raw_log.add_record(
            "[SALES EVENT]\nx", signature_verification="success"
        )


def test_lost_confirmation_is_success_not_failure(monkeypatch):
    """Append error but the row DID land -> success (a retry must not duplicate)."""

    def boom(*a, **k):
        raise RuntimeError("read timeout")

    monkeypatch.setattr(base, "append_row", boom)
    monkeypatch.setattr(telegram_raw_log, "_row_present", lambda mid: True)

    mid = telegram_raw_log.add_record(
        "[SALES EVENT]\nx", signature_verification="success"
    )
    assert mid and mid.startswith("Edgar_")


def test_happy_path_returns_message_id(monkeypatch):
    monkeypatch.setattr(base, "append_row", lambda *a, **k: {"updates": {}})
    mid = telegram_raw_log.add_record(
        "[SALES EVENT]\nx", signature_verification="success"
    )
    assert mid and mid.startswith("Edgar_")


def test_route_returns_503_when_intake_append_fails(monkeypatch):
    """The failure must reach the submitter as a retryable non-2xx, not 200."""

    def boom(*a, **k):
        raise telegram_raw_log.AppendFailure("intake append unconfirmed")

    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "message": "ok"})
    monkeypatch.setattr(telegram_raw_log, "add_record", boom)
    monkeypatch.setattr(dispatch, "dispatch_event", lambda text: None)

    signed = (
        "[SALES EVENT]\nItem: QR123\n--------\n"
        "My Digital Signature: PUBKEY\nRequest Transaction ID: SIG123=="
    )
    r = client.post("/dao/submit_contribution", data={"text": signed})
    assert r.status_code == 503
    assert r.json()["error"] == "intake_append_failed"
    assert r.json()["signature_verification"] == "success"


def test_route_still_200_on_success(monkeypatch):
    """No behaviour change for the happy path."""
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "message": "ok"})
    monkeypatch.setattr(
        telegram_raw_log, "add_record", lambda text, **k: "Edgar_test_001"
    )
    monkeypatch.setattr(dispatch, "dispatch_event", lambda text: None)

    signed = (
        "[SALES EVENT]\nItem: QR123\n--------\n"
        "My Digital Signature: PUBKEY\nRequest Transaction ID: SIG123=="
    )
    r = client.post("/dao/submit_contribution", data={"text": signed})
    assert r.status_code == 200
    assert r.json()["signature_verification"] == "success"
