"""Bugsnag wiring: no-op when the key is unset; configured + middleware added when set."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from truesight_dao_client.server import main
from truesight_dao_client.server.config import Settings


def _settings(**over) -> Settings:
    base = dict(environment="production", bugsnag_api_key="")
    base.update(over)
    return Settings(**base)


def test_no_key_means_no_bugsnag(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    app = main.create_app()
    assert not any("Bugsnag" in m.cls.__name__ for m in app.user_middleware)


def test_key_configures_and_adds_middleware(monkeypatch):
    captured = {}
    import bugsnag

    monkeypatch.setattr(bugsnag, "configure", lambda **kw: captured.update(kw))
    monkeypatch.setattr(main, "get_settings", lambda: _settings(bugsnag_api_key="abc123"))
    app = main.create_app()
    assert captured["api_key"] == "abc123"
    assert captured["release_stage"] == "production"
    assert any("Bugsnag" in m.cls.__name__ for m in app.user_middleware)
