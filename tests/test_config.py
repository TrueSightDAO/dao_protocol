"""Service-account path resolution: the server must locate its credential
files wherever it is deployed (Edgar box, autopilot EC2, dao_protocol host)
instead of hardcoding a path that only exists on one of them.

Regression for the 2026-05-29 `[Errno 2] No such file or directory:
'/home/ubuntu/sentiment_importer/config/edgar_dapp_listener_key.json'` failure
seen when the DApp registration ran on the autopilot box, where that absolute
Edgar-box path does not exist (the key lives under config/google there).
"""

from __future__ import annotations

import pytest

from truesight_dao_client.server import config
from truesight_dao_client.server.config import Settings

_FILENAMES = {
    "google_sa_json": "edgar_dapp_listener_key.json",
    "google_sa_json_qr_lookup": "cypher_defense_gdrive_key.json",
    "google_sa_json_qr_sales": "agroverse_qr_code_gdrive_key.json",
}


@pytest.fixture(autouse=True)
def _clear_creds_env(monkeypatch):
    # Keep the host's real GOOGLE_CREDS_DIR / built-in dirs out of the way so
    # tests are deterministic regardless of where they run.
    monkeypatch.delenv("GOOGLE_CREDS_DIR", raising=False)
    monkeypatch.setattr(config, "_BUILTIN_CREDS_DIRS", ())


def _write_keys(directory):
    for name in _FILENAMES.values():
        (directory / name).write_text("{}")


def test_resolves_from_google_creds_dir(tmp_path):
    _write_keys(tmp_path)
    s = Settings(google_creds_dir=str(tmp_path))
    for field, filename in _FILENAMES.items():
        assert getattr(s, field) == str(tmp_path / filename)


def test_resolves_from_google_creds_dir_env(tmp_path, monkeypatch):
    _write_keys(tmp_path)
    monkeypatch.setenv("GOOGLE_CREDS_DIR", str(tmp_path))
    s = Settings()
    assert s.google_sa_json == str(tmp_path / "edgar_dapp_listener_key.json")


def test_explicit_override_wins_verbatim(tmp_path):
    _write_keys(tmp_path)
    pinned = "/some/exact/path/edgar_dapp_listener_key.json"
    s = Settings(google_creds_dir=str(tmp_path), google_sa_json=pinned)
    # Pinned key is respected even though it does not exist on disk...
    assert s.google_sa_json == pinned
    # ...while the others still auto-resolve from the creds dir.
    assert s.google_sa_json_qr_lookup == str(tmp_path / "cypher_defense_gdrive_key.json")


def test_falls_back_to_legacy_path_when_nothing_exists(tmp_path):
    # Empty creds dir (no key files), no built-ins: should name the legacy path
    # so the eventual error is actionable rather than empty.
    s = Settings(google_creds_dir=str(tmp_path))
    assert s.google_sa_json == f"{config._LEGACY_CREDS_DIR}/edgar_dapp_listener_key.json"
