"""Tests for the deferred-gap ports: inventory-snapshot enqueue + /dao attachment→GitHub upload."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from truesight_dao_client.server import dispatch
from truesight_dao_client.server.jobs import inventory_snapshot
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import dao
from truesight_dao_client.server.services import github_upload
from truesight_dao_client.server.sheets import telegram_raw_log

client = TestClient(create_app())


# --- inventory snapshot ---
def test_inventory_publish_configured(monkeypatch):
    monkeypatch.setattr(inventory_snapshot, "get_settings", lambda: SimpleNamespace(
        agroverse_inventory_gas_webapp_url="https://script.google.com/x/exec",
        agroverse_inventory_publish_secret="sek",
        agroverse_inventory_gas_action="recalculateAndPublishInventory"))
    captured = {}
    monkeypatch.setattr(inventory_snapshot.requests, "get",
                        lambda url, timeout: captured.update(url=url) or SimpleNamespace(ok=True, status_code=200))
    assert inventory_snapshot.publish() is True
    assert "action=recalculateAndPublishInventory" in captured["url"] and "token=sek" in captured["url"]


def test_inventory_publish_unconfigured(monkeypatch):
    monkeypatch.setattr(inventory_snapshot, "get_settings", lambda: SimpleNamespace(
        agroverse_inventory_gas_webapp_url="", agroverse_inventory_publish_secret="",
        agroverse_inventory_gas_action="recalculateAndPublishInventory"))
    assert inventory_snapshot.publish() is False


def test_asset_receipt_triggers_inventory(monkeypatch):
    called = {}
    monkeypatch.setattr(dispatch.inventory_snapshot, "publish", lambda: called.update(p=True))
    monkeypatch.setattr(dispatch.webhook_trigger, "trigger", lambda *a, **k: True)
    dispatch.dispatch_event("[ASSET RECEIPT EVENT]\nCurrency: X")
    assert called.get("p") is True


def test_sales_inventory_expense_events_trigger_inventory_snapshot(monkeypatch):
    # Rails sets enqueue_agroverse_inventory_snapshot:true on SALES_AGL4/NON_AGL4,
    # INVENTORY_PROCESSING, EXPENSE_PROCESSING. Python collapses to one event-level enqueue.
    for tag in ("[SALES EVENT]", "[INVENTORY MOVEMENT]", "[DAO Inventory Expense Event]"):
        called = {}
        monkeypatch.setattr(dispatch.inventory_snapshot, "publish", lambda: called.update(p=True))
        monkeypatch.setattr(dispatch.webhook_trigger, "trigger", lambda *a, **k: True)
        dispatch.dispatch_event(tag + "\n- x: y")
        assert called.get("p") is True, f"{tag} must fire the inventory snapshot enqueue"


def test_non_inventory_event_does_not_trigger_snapshot(monkeypatch):
    # An event with no inventory implication must NOT enqueue the snapshot.
    called = {}
    monkeypatch.setattr(dispatch.inventory_snapshot, "publish", lambda: called.update(p=True))
    monkeypatch.setattr(dispatch.webhook_trigger, "trigger", lambda *a, **k: True)
    dispatch.dispatch_event("[CREDENTIALING ATTESTATION EVENT]\n- x: y")
    assert called.get("p") is None


# --- github upload ---
def _settings_pat(pat="testpat"):
    return SimpleNamespace(github_pat=pat)


def test_github_upload_creates_when_404(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    monkeypatch.setattr(github_upload.requests, "get", lambda *a, **k: SimpleNamespace(status_code=404))
    put_called = {}
    monkeypatch.setattr(github_upload.requests, "put",
                        lambda *a, **k: put_called.update(body=k.get("json")) or SimpleNamespace(status_code=201))
    text = "Receipt at https://github.com/TrueSightDAO/.github/blob/main/assets/r.pdf"
    assert github_upload.upload_if_referenced(text, b"PDFBYTES") is True
    assert put_called["body"]["branch"] == "main"


def test_github_upload_exists_when_200(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    monkeypatch.setattr(github_upload.requests, "get", lambda *a, **k: SimpleNamespace(status_code=200))
    text = "https://github.com/TrueSightDAO/.github/blob/main/assets/r.pdf"
    assert github_upload.upload_if_referenced(text, b"x") is True


def test_github_upload_no_url_or_pat(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    assert github_upload.upload_if_referenced("no url here", b"x") is False
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat(""))
    assert github_upload.upload_if_referenced("https://github.com/o/r/blob/main/p", b"x") is False


# --- /dao route attachment wiring ---
def test_dao_attachment_sets_flag(monkeypatch):
    monkeypatch.setattr(telegram_raw_log, "add_record", lambda *a, **k: True)
    monkeypatch.setattr(dao.github_upload, "upload_if_referenced", lambda text, b, fn=None: True)
    r = client.post("/dao/submit_contribution",
                    data={"text": "see https://github.com/TrueSightDAO/.github/blob/main/assets/x.pdf"},
                    files={"attachment": ("x.pdf", b"bytes", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["fileUploadedToGithub"] is True
