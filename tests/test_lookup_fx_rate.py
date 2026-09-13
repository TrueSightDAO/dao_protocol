"""Tests for the read-only FX-rate lookup CLI.

Network is monkeypatched - these tests never hit a live endpoint.
"""

from __future__ import annotations

import pytest

from truesight_dao_client.modules import lookup_fx_rate as fx


def test_get_rate_live(monkeypatch):
    def fake(url, timeout=20.0):
        assert "open.er-api.com" in url
        return {
            "result": "success",
            "base_code": "USD",
            "time_last_update_utc": "Sun, 13 Sep 2026 00:02:31 +0000",
            "rates": {"BRL": 5.105333, "CNY": 7.1},
        }

    monkeypatch.setattr(fx, "_get_json", fake)
    data = fx.get_rate("usd", "brl")
    assert data["base"] == "USD"
    assert data["quote"] == "BRL"
    assert data["rate"] == pytest.approx(5.105333)
    assert "er-api" in data["source"]


def test_get_rate_historical(monkeypatch):
    seen = {}

    def fake(url, timeout=20.0):
        seen["url"] = url
        return {"base": "USD", "date": "2026-09-11", "rates": {"BRL": 5.1108}}

    monkeypatch.setattr(fx, "_get_json", fake)
    data = fx.get_rate("USD", "BRL", date="20260912")
    assert "frankfurter.dev" in seen["url"]
    assert "2026-09-12" in seen["url"]
    assert data["date"] == "2026-09-11"
    assert data["rate"] == pytest.approx(5.1108)


def test_missing_quote_raises(monkeypatch):
    monkeypatch.setattr(
        fx, "_get_json", lambda url, timeout=20.0: {"base_code": "USD", "rates": {}}
    )
    with pytest.raises(KeyError):
        fx.get_rate("USD", "ZZZ")


def test_error_payload_raises(monkeypatch):
    monkeypatch.setattr(
        fx,
        "_get_json",
        lambda url, timeout=20.0: {"result": "error", "error-type": "unsupported-code"},
    )
    with pytest.raises(RuntimeError):
        fx.fetch_rates("NOPE")


def test_implied_rate_string_matches_conversion_cli():
    assert fx.implied_rate_string("usd", "brl", 5.105333) == "1 USD = 5.105333 BRL"


def test_main_stale_handroll_flags(monkeypatch, capsys):
    monkeypatch.setattr(
        fx,
        "_get_json",
        lambda url, timeout=20.0: {
            "result": "success",
            "base_code": "USD",
            "rates": {"BRL": 5.0},
        },
    )
    rc = fx.main(
        [
            "--base",
            "USD",
            "--quote",
            "BRL",
            "--compare-source-amount",
            "1000",
            "--compare-target-amount",
            "4305",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "HAND-ROLLED RATE IS STALE" in out


def test_main_ok_handroll(monkeypatch, capsys):
    monkeypatch.setattr(
        fx,
        "_get_json",
        lambda url, timeout=20.0: {
            "result": "success",
            "base_code": "USD",
            "rates": {"BRL": 5.0},
        },
    )
    rc = fx.main(
        [
            "--base",
            "USD",
            "--quote",
            "BRL",
            "--compare-source-amount",
            "500",
            "--compare-target-amount",
            "2505",
        ]
    )
    assert rc == 0
    assert "[OK]" in capsys.readouterr().out


def test_main_json(monkeypatch, capsys):
    monkeypatch.setattr(
        fx,
        "_get_json",
        lambda url, timeout=20.0: {
            "result": "success",
            "base_code": "USD",
            "rates": {"BRL": 5.0},
        },
    )
    assert fx.main(["--base", "USD", "--quote", "BRL", "--json"]) == 0
    assert '"rate": 5.0' in capsys.readouterr().out


def test_main_lookup_failure_exit_1(monkeypatch, capsys):
    def boom(url, timeout=20.0):
        raise RuntimeError("network down")

    monkeypatch.setattr(fx, "_get_json", boom)
    assert fx.main(["--base", "USD", "--quote", "BRL"]) == 1
    assert "Rate lookup failed" in capsys.readouterr().err
