#!/usr/bin/env python3
"""
Reader for DAO member info — voting rights + contributor name lookups.

**Two backends, swappable via `_default_lookup_source()`:**

1. **GAS assetVerify** (legacy; default today) — same endpoint `dapp/tdg_balance.js`
   used pre-cache. Per-public-key query; returns one record. Slower (2–5 s cold
   start) and no list support.
2. **GitHub raw `dao_members.json`** — contributor-aggregated snapshot published
   by `tokenomics/google_app_scripts/tdg_identity_management/dao_members_cache_publisher.gs`.
   Fires on every `[EMAIL VERIFICATION EVENT]` activation (via
   `sentiment_importer`'s `DaoMembersCacheRefreshWorker`) plus a daily
   safety-net cron. Enables `list_all()` and faster lookups.

The module auto-detects which shape came back — GAS returns a dict with
`contributor_name`; GitHub returns a dict with `contributors[]`. Callers
(`for_self()`, `for_public_key()`, `list_all()`) keep identical signatures.

Snapshot shape (GitHub backend, schema_version 2):

    {
      "generated_at": "2026-04-21T…Z",
      "schema_version": 2,
      "dao_totals": {
        "voting_rights_circulated": N,
        "total_assets": N,
        "asset_per_circulated_voting_right": N,
        "usd_provisions_for_cash_out": N
      },
      "contributors": [
        {"name": "Gary Teh", "voting_rights": N,
         "public_keys": [{"public_key": "MIIB…", "status": "ACTIVE",
                          "created_at": "…", "last_active_at": "…"}]}
      ]
    }

One contributor has N active public keys (see `agentic_ai_context` memory
`project_edgar_multiple_active_keys`), so the lookup scans
`contributors[*].public_keys[*]`.

CLI:
    python -m truesight_dao_client.cache.contributors                      # look up self via .env PUBLIC_KEY
    python -m truesight_dao_client.cache.contributors --pubkey MIIB...     # look up someone else
    python -m truesight_dao_client.cache.contributors --list               # full roster (GitHub backend only)
    python -m truesight_dao_client.cache.contributors --github             # force GitHub backend even if default is GAS
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from ..edgar_client import EdgarClient
from ._source import DataSource, GasBackend, GithubRawBackend


# `assetVerify` GAS web app (see dapp/tdg_balance.js). `full=true` returns the
# expanded record: voting_rights, asset_per_circulated_voting_right, etc.
GAS_EXEC_URL = "https://script.google.com/macros/s/AKfycbygmwRbyqse-dpCYMco0rb93NSgg-Jc1QIw7kUiBM7CZK6jnWnMB5DEjdoX_eCsvVs7/exec"

# GitHub-raw snapshot published by
# tokenomics/google_app_scripts/tdg_identity_management/dao_members_cache_publisher.gs.
GITHUB_RAW_URL = "https://raw.githubusercontent.com/TrueSightDAO/treasury-cache/main/dao_members.json"


def _default_lookup_source() -> DataSource:
    """Flip to `_github_lookup_source()` once operators have confirmed the
    GitHub cache is being refreshed on verification + daily cron."""
    return GasBackend(GAS_EXEC_URL, base_params={"full": "true"})


def _github_lookup_source() -> DataSource:
    return GithubRawBackend(GITHUB_RAW_URL)


@dataclass
class Contributors:
    """Per-public-key voting-rights lookups + full roster (if GitHub-backed)."""

    source: DataSource = field(default_factory=_default_lookup_source)

    @classmethod
    def from_github(cls) -> "Contributors":
        return cls(source=_github_lookup_source())

    # ---- lookups -----------------------------------------------------------

    def for_public_key(self, public_key_b64: str) -> dict[str, Any]:
        data = self.source.fetch(signature=public_key_b64)
        # GAS shape: single-record dict with contributor_name.
        if isinstance(data, dict) and data.get("contributor_name") is not None:
            return {**data, "_source": "gas"}
        # GitHub shape: snapshot root with contributors[].
        if isinstance(data, dict) and "contributors" in data:
            return _lookup_in_snapshot(data, public_key_b64)
        raise RuntimeError(f"Unexpected response shape (keys: {list(data.keys()) if isinstance(data, dict) else type(data)})")

    def for_self(self) -> dict[str, Any]:
        client = EdgarClient.from_env()
        return self.for_public_key(client.public_key_b64)

    # ---- list ---------------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        data = self.source.fetch()
        if isinstance(data, dict) and "contributors" in data:
            return list(data.get("contributors") or [])
        raise NotImplementedError(
            "list_all() requires the GitHub cache backend. "
            "Use `Contributors.from_github().list_all()` or flip _default_lookup_source() "
            "to _github_lookup_source() once operators confirm dao_members.json is being refreshed."
        )

    def dao_totals(self) -> dict[str, Any]:
        """DAO-wide aggregates (GitHub backend only). Raises on GAS backend."""
        data = self.source.fetch()
        if isinstance(data, dict) and "dao_totals" in data:
            return dict(data.get("dao_totals") or {})
        raise NotImplementedError("dao_totals() requires the GitHub cache backend.")


def _lookup_in_snapshot(snapshot: dict[str, Any], public_key_b64: str) -> dict[str, Any]:
    """Scan contributors[*].public_keys[*] for a match and merge DAO-wide totals."""
    totals = dict(snapshot.get("dao_totals") or {})
    for contributor in snapshot.get("contributors") or []:
        for key_entry in contributor.get("public_keys") or []:
            if key_entry.get("public_key") == public_key_b64:
                return {
                    "contributor_name": contributor.get("name"),
                    "roles": contributor.get("roles"),
                    "voting_rights": contributor.get("voting_rights"),
                    "voting_rights_circulated": totals.get("voting_rights_circulated"),
                    "total_assets": totals.get("total_assets"),
                    "asset_per_circulated_voting_right": totals.get("asset_per_circulated_voting_right"),
                    "usd_provisions_for_cash_out": totals.get("usd_provisions_for_cash_out"),
                    "public_key": public_key_b64,
                    "key_status": key_entry.get("status"),
                    "_source": "github_cache",
                    "_generated_at": snapshot.get("generated_at"),
                }
    return {
        "error": "Public key not found in dao_members.json snapshot",
        "public_key": public_key_b64,
        "_source": "github_cache",
        "_generated_at": snapshot.get("generated_at"),
    }


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Look up DAO contributor voting rights / name.")
    p.add_argument("--github", action="store_true",
                   help="Force the GitHub-raw backend (dao_members.json). Default: GAS assetVerify.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pubkey", help="SPKI base64 public key to look up.")
    g.add_argument("--list", action="store_true", help="Print the full roster (GitHub backend).")
    g.add_argument("--totals", action="store_true", help="Print DAO-wide totals (GitHub backend).")
    args = p.parse_args(argv)

    contributors = Contributors.from_github() if args.github else Contributors()

    if args.list:
        print(json.dumps(contributors.list_all(), indent=2))
        return 0
    if args.totals:
        print(json.dumps(contributors.dao_totals(), indent=2))
        return 0

    record = contributors.for_public_key(args.pubkey) if args.pubkey else contributors.for_self()
    print(json.dumps(record, indent=2))
    return 0


main = _cli

if __name__ == "__main__":
    sys.exit(_cli())
