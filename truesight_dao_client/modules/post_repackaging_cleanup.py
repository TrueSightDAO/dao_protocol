#!/usr/bin/env python3
"""Post-Repackaging Cleanup — auto-populate Currencies + offchain asset location.

Closes the gap between ``[REPACKAGING BATCH EVENT]`` submission and a fully
populated Main Ledger.  The repackaging GAS writes only Currencies columns
A, B, N, O.  This module handles the remaining four cleanup steps:

  1. Deplete consumed inputs from ``offchain asset location``
  2. Add output rows to ``offchain asset location``
  3. Set ``Currencies`` columns C (isSerializable), E–J (farm info), M (SKU)
  4. Optionally rebuild ``store-inventory.json``

Usage:
    python -m truesight_dao_client.modules.post_repackaging_cleanup \\
        --composition-url <URL> --holder-name "Kirsten Ritschel" \\
        --sku-mapping '{"Ceremonial Cacao Kraft Pouch": "..."}' \\
        --landing-page https://agroverse.com/shop \\
        --ledger https://ledger.truesight.me \\
        --farm-name "Fazenda Santa Clara" --state Bahia \\
        --country Brazil --year 2026 --dry-run

Requires:
- ``google_credentials.json`` with editor access to the Main Ledger
  (``1GE7PUq-…``).  Searched in the same order as ``onboard_partner.py``:
    1. ``$DAO_CLIENT_GOOGLE_CREDENTIALS`` env var
    2. ``dao_client/google_credentials.json``
    3. ``../market_research/google_credentials.json``
- ``gspread`` and ``google-auth`` (``pip install gspread google-auth``)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests

MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
OFFCHAIN_SHEET_GID = 1883963235  # "offchain asset location"
CURRENCIES_SHEET_GID = 1552160318  # "Currencies"

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Google Sheets helpers (gspread) — mirrors onboard_partner.py
# ---------------------------------------------------------------------------

def _find_google_credentials() -> Path:
    env = os.environ.get("DAO_CLIENT_GOOGLE_CREDENTIALS")
    if env and Path(env).is_file():
        return Path(env)
    here = REPO_ROOT / "google_credentials.json"
    if here.is_file():
        return here
    sibling = REPO_ROOT.parent / "market_research" / "google_credentials.json"
    if sibling.is_file():
        return sibling
    raise SystemExit(
        "google_credentials.json not found. Set DAO_CLIENT_GOOGLE_CREDENTIALS, "
        "place it at dao_client/google_credentials.json, or have a sibling "
        "market_research/google_credentials.json checkout."
    )


def _gspread_client():
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials as SACreds  # type: ignore
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency for sheet operations: {e}. "
            "pip install gspread google-auth"
        )
    creds = SACreds.from_service_account_file(
        str(_find_google_credentials()),
        scopes=(
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ),
    )
    return gspread.authorize(creds)


def _retry(fn, *, attempts: int = 5, base_delay: float = 1.0):
    """Tiny retry for Sheets transient errors. Mirrors onboard_partner.py."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(base_delay * (2**i))
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Composition JSON fetching + validation
# ---------------------------------------------------------------------------

def _fetch_composition(url: str) -> dict[str, Any]:
    """Fetch and validate a composition JSON from a URL."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "inputs" not in data or "outputs" not in data:
        raise ValueError(
            "Composition JSON must contain 'inputs' and 'outputs' arrays. "
            f"Got keys: {list(data.keys())}"
        )
    if "request_id" not in data:
        data["request_id"] = "unknown"
    return data


# ---------------------------------------------------------------------------
# Sheet operations
# ---------------------------------------------------------------------------

def _find_row_by_col_a(worksheet, value: str) -> int | None:
    """Return the 1-based row index where column A equals ``value``, or None."""
    col_a = worksheet.col_values(1)  # 1-based: column A
    for i, cell in enumerate(col_a, start=1):
        if cell.strip() == value:
            return i
    return None


def _find_offchain_row(worksheet, currency: str, holder: str) -> int | None:
    """Find row in offchain asset location where col A = currency AND col B = holder."""
    data = worksheet.get_all_values()
    for i, row in enumerate(data, start=1):
        if len(row) >= 2 and row[0].strip() == currency and row[1].strip() == holder:
            return i
    return None


def _deplete_inputs(
    worksheet, composition: dict[str, Any], holder: str, *, dry_run: bool, verbose: bool
) -> list[str]:
    """Deplete consumed inputs from offchain asset location.

    Only depletes rows where ``line_kind == 'from_holder_inventory'``.
    Returns a list of summary lines for the final report.
    """
    summary: list[str] = []
    for inp in composition.get("inputs", []):
        if inp.get("line_kind") != "from_holder_inventory":
            continue
        currency = inp["currency"]
        qty = inp["quantity"]
        row_idx = _find_offchain_row(worksheet, currency, holder)
        if row_idx is None:
            msg = f"  ⚠  DEPLETION: row not found for '{currency}' @ '{holder}' — skipped"
            summary.append(msg)
            if verbose:
                print(msg)
            continue
        # Read current amount (col C)
        current_str = worksheet.cell(row_idx, 3).value or "0"
        try:
            current = float(current_str)
        except ValueError:
            current = 0.0
        new_amount = max(0.0, current - qty)
        if dry_run:
            msg = f"  ~  DEPLETION: '{currency}' {current} → {new_amount} (row {row_idx})"
        else:
            worksheet.update_cell(row_idx, 3, str(new_amount))
            msg = f"  ✓  DEPLETION: '{currency}' {current} → {new_amount} (row {row_idx})"
        summary.append(msg)
        if verbose:
            print(msg)
    return summary


def _add_output_locations(
    worksheet, composition: dict[str, Any], holder: str, *, dry_run: bool, verbose: bool
) -> list[str]:
    """Append output rows to offchain asset location."""
    summary: list[str] = []
    for out in composition.get("outputs", []):
        currency = out["suggested_currency"]
        units = out["units"]
        unit_cost = out.get("unit_cost_usd", "")
        line_total = out.get("line_total_usd", "")
        new_row = [currency, holder, str(units), str(unit_cost), str(line_total)]
        if dry_run:
            msg = f"  ~  ADD LOCATION: '{currency}' × {units} @ {holder}"
        else:
            worksheet.append_row(new_row, value_input_option="USER_ENTERED")
            msg = f"  ✓  ADD LOCATION: '{currency}' × {units} @ {holder}"
        summary.append(msg)
        if verbose:
            print(msg)
    return summary


def _set_currencies_metadata(
    worksheet,
    composition: dict[str, Any],
    *,
    sku_mapping: dict[str, str] | None,
    landing_page: str | None,
    ledger: str | None,
    farm_name: str | None,
    state: str | None,
    country: str | None,
    year: str | None,
    dry_run: bool,
    verbose: bool,
) -> list[str]:
    """Set Currencies metadata columns C, E, F, G, H, I, J, M for each output.

    Column mapping (1-based):
      C=3  (isSerializable → "TRUE")
      E=5  (landing_page)
      F=6  (ledger)
      G=7  (farm name)
      H=8  (state)
      I=9  (country)
      J=10 (year)
      M=13 (SKU Product ID)
    """
    summary: list[str] = []
    for out in composition.get("outputs", []):
        currency = out["suggested_currency"]
        row_idx = _find_row_by_col_a(worksheet, currency)
        if row_idx is None:
            msg = f"  ⚠  CURRENCIES: row not found for '{currency}' — skipped (GAS may not have run)"
            summary.append(msg)
            if verbose:
                print(msg)
            continue

        updates: dict[int, str] = {}
        updates[3] = "TRUE"  # C: isSerializable
        if landing_page:
            updates[5] = landing_page
        if ledger:
            updates[6] = ledger
        if farm_name:
            updates[7] = farm_name
        if state:
            updates[8] = state
        if country:
            updates[9] = country
        if year:
            updates[10] = year
        if sku_mapping:
            sku_id = _match_sku(currency, sku_mapping)
            if sku_id:
                updates[13] = sku_id
            else:
                msg_sku = f"  ⚠  SKU: no mapping matched '{currency}' — col M left empty"
                summary.append(msg_sku)
                if verbose:
                    print(msg_sku)

        if dry_run:
            cols_str = ", ".join(f"{col}={val}" for col, val in sorted(updates.items()))
            msg = f"  ~  CURRENCIES: '{currency}' (row {row_idx}) → {cols_str}"
        else:
            for col, val in updates.items():
                worksheet.update_cell(row_idx, col, val)
            msg = f"  ✓  CURRENCIES: '{currency}' (row {row_idx}) — {len(updates)} cols updated"
        summary.append(msg)
        if verbose:
            print(msg)
    return summary


def _match_sku(currency: str, mapping: dict[str, str]) -> str | None:
    """Return the first SKU ID whose key is a substring of ``currency``."""
    for pattern, sku_id in mapping.items():
        if pattern.lower() in currency.lower():
            return sku_id
    return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(
    composition_url: str,
    *,
    holder_name: str | None,
    sku_mapping: dict[str, str] | None,
    landing_page: str | None,
    ledger: str | None,
    farm_name: str | None,
    state: str | None,
    country: str | None,
    year: str | None,
    deplete_inputs: bool,
    add_output_locations: bool,
    set_currencies_metadata: bool,
    rebuild_inventory: bool,
    spreadsheet_id: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Execute the post-repackaging cleanup workflow."""
    label = "DRY RUN" if dry_run else "EXECUTE"
    print(f"=== Post-Repackaging Cleanup [{label}] ===")
    print(f"  composition: {composition_url}")
    print(f"  holder:      {holder_name or '(not set — skipping location ops)'}")
    print()

    # 1. Fetch composition
    print("--- Step 1: Fetch composition ---")
    composition = _fetch_composition(composition_url)
    print(f"  request_id: {composition.get('request_id', 'unknown')}")
    print(f"  inputs:  {len(composition.get('inputs', []))} lines")
    print(f"  outputs: {len(composition.get('outputs', []))} lines")
    print()

    # 2. Open sheets
    print("--- Step 2: Open sheets ---")
    gc = _gspread_client()
    sh = _retry(lambda: gc.open_by_key(spreadsheet_id))
    offchain = _retry(lambda: sh.get_worksheet_by_id(OFFCHAIN_SHEET_GID))
    currencies = _retry(lambda: sh.get_worksheet_by_id(CURRENCIES_SHEET_GID))
    print(f"  offchain asset location: {offchain.title} (gid={OFFCHAIN_SHEET_GID})")
    print(f"  Currencies:              {currencies.title} (gid={CURRENCIES_SHEET_GID})")
    print()

    all_summaries: list[str] = []

    # 3. Deplete inputs
    if deplete_inputs and holder_name:
        print("--- Step 3: Deplete inputs from offchain asset location ---")
        s = _deplete_inputs(offchain, composition, holder_name, dry_run=dry_run, verbose=verbose)
        all_summaries.extend(s)
        print()
    elif deplete_inputs and not holder_name:
        print("--- Step 3: Deplete inputs — SKIPPED (no --holder-name) ---")
        print()
    else:
        print("--- Step 3: Deplete inputs — SKIPPED (--no-deplete-inputs) ---")
        print()

    # 4. Add output locations
    if add_output_locations and holder_name:
        print("--- Step 4: Add output rows to offchain asset location ---")
        s = _add_output_locations(offchain, composition, holder_name, dry_run=dry_run, verbose=verbose)
        all_summaries.extend(s)
        print()
    elif add_output_locations and not holder_name:
        print("--- Step 4: Add output locations — SKIPPED (no --holder-name) ---")
        print()
    else:
        print("--- Step 4: Add output locations — SKIPPED (--no-add-output-locations) ---")
        print()

    # 5. Set Currencies metadata
    if set_currencies_metadata:
        print("--- Step 5: Set Currencies metadata ---")
        s = _set_currencies_metadata(
            currencies,
            composition,
            sku_mapping=sku_mapping,
            landing_page=landing_page,
            ledger=ledger,
            farm_name=farm_name,
            state=state,
            country=country,
            year=year,
            dry_run=dry_run,
            verbose=verbose,
        )
        all_summaries.extend(s)
        print()
    else:
        print("--- Step 5: Set Currencies metadata — SKIPPED (--no-set-currencies-metadata) ---")
        print()

    # 6. Rebuild inventory (opt-in)
    if rebuild_inventory:
        print("--- Step 6: Rebuild store-inventory.json ---")
        if dry_run:
            print("  ~  Would run: sync_agroverse_store_inventory.py (dry-run, skipped)")
        else:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "truesight_dao_client.modules.sync_agroverse_store_inventory"],
                    capture_output=True, text=True, timeout=120,
                )
                print(f"  ✓  Inventory sync exit code: {result.returncode}")
                if result.stdout:
                    print(result.stdout[:500])
                if result.stderr:
                    print(f"  stderr: {result.stderr[:300]}")
            except FileNotFoundError:
                print("  ⚠  sync_agroverse_store_inventory module not found — skipped")
            except subprocess.TimeoutExpired:
                print("  ⚠  Inventory sync timed out after 120s — skipped")
        print()
    else:
        print("--- Step 6: Rebuild inventory — SKIPPED (use --rebuild-inventory to enable) ---")
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if all_summaries:
        for line in all_summaries:
            print(line)
    else:
        print("  (no operations performed)")
    print()
    if dry_run:
        print("🔶 DRY RUN — no changes were written. Re-run with --execute to apply.")
    else:
        print("✅ Cleanup complete.")


def _parse_sku_mapping(raw: str | None) -> dict[str, str] | None:
    """Parse --sku-mapping JSON string into a dict."""
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("--sku-mapping must be a JSON object")
        return {str(k): str(v) for k, v in parsed.items()}
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid --sku-mapping JSON: {e}")


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Post-Repackaging Cleanup — auto-populate Currencies + offchain asset location.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  %(prog)s --composition-url https://... --holder-name \"Kirsten Ritschel\" \\n"
            "    --sku-mapping '{\"Ceremonial Cacao\": \"ceremonial-cacao-pouch\"}' \\n"
            "    --landing-page https://agroverse.com/shop --dry-run\n"
        ),
    )
    p.add_argument(
        "--composition-url", required=True,
        help="URL to composition JSON (GitHub raw or any HTTP endpoint).",
    )
    p.add_argument(
        "--holder-name", default=None,
        help="Who physically holds the inventory (required for deplete/add-location ops).",
    )
    p.add_argument(
        "--sku-mapping", default=None,
        help='JSON object mapping output label substrings to SKU IDs, e.g. '
             '{"Ceremonial Cacao Kraft Pouch": "ceremonial-cacao-kraft-pouch-200g"}',
    )
    p.add_argument("--landing-page", default=None, help="Landing page URL for Currencies!E")
    p.add_argument("--ledger", default=None, help="Ledger URL for Currencies!F")
    p.add_argument("--farm-name", default=None, help="Farm name for Currencies!G")
    p.add_argument("--state", default=None, help="State for Currencies!H")
    p.add_argument("--country", default=None, help="Country for Currencies!I")
    p.add_argument("--year", default=None, help="Year for Currencies!J")

    p.add_argument(
        "--deplete-inputs", action="store_true", default=True,
        help="Deplete consumed inputs from offchain asset location (default).",
    )
    p.add_argument(
        "--no-deplete-inputs", action="store_false", dest="deplete_inputs",
        help="Skip input depletion.",
    )
    p.add_argument(
        "--add-output-locations", action="store_true", default=True,
        help="Add output rows to offchain asset location (default).",
    )
    p.add_argument(
        "--no-add-output-locations", action="store_false", dest="add_output_locations",
        help="Skip adding output locations.",
    )
    p.add_argument(
        "--set-currencies-metadata", action="store_true", default=True,
        help="Set Currencies metadata columns C, E–J, M (default).",
    )
    p.add_argument(
        "--no-set-currencies-metadata", action="store_false", dest="set_currencies_metadata",
        help="Skip Currencies metadata update.",
    )
    p.add_argument(
        "--rebuild-inventory", action="store_true", default=False,
        help="Also rebuild store-inventory.json (opt-in, default off).",
    )

    p.add_argument(
        "--spreadsheet-id", default=MAIN_LEDGER_ID,
        help=f"Override Main Ledger spreadsheet ID (default: {MAIN_LEDGER_ID[:20]}...).",
    )

    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Validate, resolve, print what WOULD be written — don't write (default).",
    )
    g.add_argument(
        "--execute", action="store_true",
        help="Perform side effects (sheet writes, inventory rebuild).",
    )
    p.add_argument("--verbose", action="store_true", help="Print per-row detail.")

    args = p.parse_args(argv)
    dry_run = not args.execute  # --dry-run is default

    run(
        composition_url=args.composition_url,
        holder_name=args.holder_name,
        sku_mapping=_parse_sku_mapping(args.sku_mapping),
        landing_page=args.landing_page,
        ledger=args.ledger,
        farm_name=args.farm_name,
        state=args.state,
        country=args.country,
        year=args.year,
        deplete_inputs=args.deplete_inputs,
        add_output_locations=args.add_output_locations,
        set_currencies_metadata=args.set_currencies_metadata,
        rebuild_inventory=args.rebuild_inventory,
        spreadsheet_id=args.spreadsheet_id,
        dry_run=dry_run,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
