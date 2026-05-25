"""Tests for the GAS cross-border proxy route (PR2). `requests` is mocked — no network."""

from __future__ import annotations

import requests
from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import proxy

client = TestClient(create_app())


class _FakeResp:
    def __init__(self, content=b"{}", status_code=200, content_type="application/json"):
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}


def test_options_preflight_returns_cors():
    r = client.options("/proxy/gas/qrCodes")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"
    assert "GET" in r.headers["access-control-allow-methods"]


def test_unknown_endpoint_is_404():
    r = client.get("/proxy/gas/definitelyNotAReal Endpoint".replace(" ", ""))
    assert r.status_code == 404
    assert "unknown gas endpoint" in r.json()["error"]


def test_get_forwards_raw_query_and_echoes_upstream(monkeypatch):
    captured = {}

    def fake_get(url, allow_redirects, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResp(content=b'{"ok":true}', status_code=200, content_type="application/json")

    monkeypatch.setattr(proxy.requests, "get", fake_get)
    r = client.get("/proxy/gas/qrCodes?action=lookup&qr=ABC123")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # raw query string forwarded onto the allowlisted upstream
    assert captured["url"].endswith("?action=lookup&qr=ABC123")
    assert "script.google.com" in captured["url"]
    assert captured["timeout"] == 30
    assert r.headers["access-control-allow-origin"] == "*"


def test_post_forwards_body_and_content_type(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, allow_redirects, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _FakeResp(content=b"saved", status_code=201, content_type="text/plain")

    monkeypatch.setattr(proxy.requests, "post", fake_post)
    r = client.post(
        "/proxy/gas/feedback",
        content=b"a=1&b=2",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 201           # upstream status echoed
    assert r.text == "saved"
    assert r.headers["content-type"].startswith("text/plain")
    assert captured["data"] == b"a=1&b=2"
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_upstream_failure_returns_502(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectTimeout("upstream down")

    monkeypatch.setattr(proxy.requests, "get", boom)
    r = client.get("/proxy/gas/stores?action=ping")
    assert r.status_code == 502
    assert r.json()["error"] == "upstream unavailable"
