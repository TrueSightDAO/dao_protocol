"""Tests for newsletter + email-agent tracking routes (PR3). Sheets layer mocked — no network."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import tracking
from truesight_dao_client.server.sheets import email_agent_drafts, newsletter_emails

client = TestClient(create_app(), follow_redirects=False)
LOGO = tracking.OPEN_TRACKING_LOGO_URL
FALLBACK = tracking.CLICK_FALLBACK_URL


def _b64(s: str) -> str:  # urlsafe, padding stripped (as real tracking links are built)
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_newsletter_open_redirects_to_logo_and_records(monkeypatch):
    calls = {}
    monkeypatch.setattr(newsletter_emails, "record_open",
                        lambda mid, recipient_email=None: calls.update(mid=mid, r=recipient_email) or True)
    resp = client.get(f"/newsletter/open.gif?mid=abc-123&r={_b64('Foo@Bar.com')}")
    assert resp.status_code == 302
    assert resp.headers["location"] == LOGO
    assert "no-store" in resp.headers["cache-control"]
    assert calls == {"mid": "abc-123", "r": "Foo@Bar.com"}   # recipient b64-decoded


def test_newsletter_click_redirects_to_target(monkeypatch):
    monkeypatch.setattr(newsletter_emails, "record_click", lambda *a, **k: True)
    target = "https://agroverse.shop/blog/post"
    resp = client.get(f"/newsletter/click?mid=m1&to={_b64(target)}")
    assert resp.status_code == 302
    assert resp.headers["location"] == target


def test_newsletter_click_bad_url_falls_back(monkeypatch):
    monkeypatch.setattr(newsletter_emails, "record_click", lambda *a, **k: True)
    # javascript: scheme must be rejected by _safe_redirect_url → fallback
    resp = client.get(f"/newsletter/click?mid=m1&to={_b64('javascript:alert(1)')}")
    assert resp.status_code == 302
    assert resp.headers["location"] == FALLBACK


def test_newsletter_click_missing_to_falls_back(monkeypatch):
    monkeypatch.setattr(newsletter_emails, "record_click", lambda *a, **k: True)
    resp = client.get("/newsletter/click?mid=m1")
    assert resp.status_code == 302
    assert resp.headers["location"] == FALLBACK


def test_email_agent_open_records_tid(monkeypatch):
    calls = {}
    monkeypatch.setattr(email_agent_drafts, "record_open",
                        lambda tid, recipient_email=None: calls.update(tid=tid) or True)
    resp = client.get("/email_agent/open.gif?tid=sugg-9")
    assert resp.status_code == 302
    assert resp.headers["location"] == LOGO
    assert calls == {"tid": "sugg-9"}


def test_email_agent_click_redirects(monkeypatch):
    monkeypatch.setattr(email_agent_drafts, "record_click", lambda *a, **k: True)
    target = "https://example.com/x"
    resp = client.get(f"/email_agent/click?tid=s1&to={_b64(target)}")
    assert resp.status_code == 302
    assert resp.headers["location"] == target


def test_sheet_error_never_breaks_redirect(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("sheets down / no credential")
    monkeypatch.setattr(newsletter_emails, "record_open", boom)
    resp = client.get("/newsletter/open.gif?mid=whatever")
    assert resp.status_code == 302          # still redirects despite the sheet error
    assert resp.headers["location"] == LOGO
