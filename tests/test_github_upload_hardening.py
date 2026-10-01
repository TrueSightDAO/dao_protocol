"""[hardening] `_put_file` retries transient GitHub 403/5xx and falls through to PUT.

Regression for the 2026-09-30 silent attachment failure (thread 23408): a
transient 403 on the *existence-check* GET aborted the whole upload
(`fileUploadedToGithub:false`) without ever attempting the PUT, so the ledger
row was inserted while its `Destination ... File Location` URL 404'd.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from truesight_dao_client.server.services import github_upload


def _resp(status_code, text="", headers=None):
    return SimpleNamespace(status_code=status_code, text=text, headers=headers or {})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # Keep the backoff paths instant; _sleep_for() is exercised but must not block.
    monkeypatch.setattr(github_upload.time, "sleep", lambda *_: None)


def _put():
    return github_upload._put_file(
        "PAT",
        "TrueSightDAO",
        ".github",
        "main",
        "assets/x.jpg",
        b"bytes",
        "x.jpg",
        "[DAO Inventory Expense Event]",
    )


def test_get_403_then_200_recovers(monkeypatch):
    calls = {"get": 0}

    def fake_get(*a, **k):
        calls["get"] += 1
        return _resp(403, "secondary rate limit") if calls["get"] == 1 else _resp(200)

    monkeypatch.setattr(github_upload.requests, "get", fake_get)
    monkeypatch.setattr(
        github_upload.requests,
        "put",
        lambda *a, **k: pytest.fail("PUT must not run when GET recovers to 200"),
    )
    assert _put() is True
    assert calls["get"] == 2


def test_get_403_persistent_falls_through_to_put(monkeypatch):
    monkeypatch.setattr(
        github_upload.requests, "get", lambda *a, **k: _resp(403, "forbidden")
    )
    seen = {}

    def fake_put(url, **k):
        seen["put"] = True
        return _resp(201)

    monkeypatch.setattr(github_upload.requests, "put", fake_put)
    assert _put() is True
    assert seen.get("put") is True


def test_put_422_sha_is_already_present(monkeypatch):
    monkeypatch.setattr(github_upload.requests, "get", lambda *a, **k: _resp(404))
    monkeypatch.setattr(
        github_upload.requests,
        "put",
        lambda *a, **k: _resp(
            422, '{"message":"Invalid request.\\n\\n\\"sha\\" wasn\'t supplied"}'
        ),
    )
    assert _put() is True


def test_put_403_persistent_is_false(monkeypatch):
    monkeypatch.setattr(github_upload.requests, "get", lambda *a, **k: _resp(404))
    monkeypatch.setattr(
        github_upload.requests, "put", lambda *a, **k: _resp(403, "forbidden")
    )
    assert _put() is False


def test_get_403_body_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(
        github_upload.requests,
        "get",
        lambda *a, **k: _resp(403, "SECONDARY_LIMIT_MARKER"),
    )
    monkeypatch.setattr(github_upload.requests, "put", lambda *a, **k: _resp(201))
    with caplog.at_level("WARNING", logger="dao_protocol.github_upload"):
        _put()
    assert "SECONDARY_LIMIT_MARKER" in caplog.text
