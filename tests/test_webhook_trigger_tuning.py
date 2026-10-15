"""Webhook trigger must tolerate GAS cold-start latency.

Real incident 2026-10-15: `processTelegramChatLogs` attempts 1-2 timed out at the fixed
30 s ceiling before attempt 3 succeeded. The timeout/attempts are now Settings-driven
(DAO_PROTOCOL_WEBHOOK_{TIMEOUT_S,MAX_ATTEMPTS}) so operators can widen them without a code
change, and the module keeps safe defaults if Settings is unavailable.
"""

from __future__ import annotations

import requests

from truesight_dao_client.server.jobs import webhook_trigger


def test_tuning_reads_settings(monkeypatch):
    from truesight_dao_client.server import config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(webhook_timeout_s=99, webhook_max_attempts=7),
    )
    assert webhook_trigger._tuning() == (99, 7)


def test_tuning_falls_back_to_defaults_on_error(monkeypatch):
    from truesight_dao_client.server import config

    def boom():
        raise RuntimeError("no settings")

    monkeypatch.setattr(config, "get_settings", boom)
    assert webhook_trigger._tuning() == (
        webhook_trigger._DEFAULT_TIMEOUT,
        webhook_trigger._DEFAULT_MAX_ATTEMPTS,
    )


def test_trigger_retries_on_timeout_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class Resp:
        ok = True

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.Timeout("read timeout")
        return Resp()

    monkeypatch.setattr(webhook_trigger.requests, "get", fake_get)
    monkeypatch.setattr(webhook_trigger.time, "sleep", lambda *_: None)
    assert webhook_trigger.trigger("https://example/exec", "processTelegramChatLogs") is True
    assert calls["n"] == 2


def test_non_2xx_is_not_retried(monkeypatch):
    calls = {"n": 0}

    class Resp:
        ok = False
        status_code = 500

    def fake_get(*a, **k):
        calls["n"] += 1
        return Resp()

    monkeypatch.setattr(webhook_trigger.requests, "get", fake_get)
    assert webhook_trigger.trigger("https://example/exec", "x") is False
    assert calls["n"] == 1
