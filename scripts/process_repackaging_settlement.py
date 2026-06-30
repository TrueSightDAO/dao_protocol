#!/usr/bin/env python3
"""Process [REPACKAGING SETTLEMENT EVENT] entries from Telegram Chat Logs.

Reads the Telegram Chat Logs tab for unprocessed settlement events, fetches
the referenced composition JSON, and writes to the Main Ledger sheets:
  1. Depletes consumed inputs from offchain asset location
  2. Adds output rows to offchain asset location
  3. Sets Currencies metadata (isSerializable, SKU IDs, farm info)
  4. Optionally triggers inventory snapshot rebuild

This is the Python equivalent of the GAS webapp handler. Run after a
[REPACKAGING SETTLEMENT EVENT] has been submitted to Edgar and logged to
Telegram Chat Logs.

Usage:
    python3 scripts/process_repackaging_settlement.py
    python3 scripts/process_repackaging_settlement.py --process-all
    python3 scripts/process_repackaging_settlement.py --dry-run
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# ── Credentials ──────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]

TELEGRAM_SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
TELEGRAM_SHEET = "Telegram Chat Logs"

MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
OFFCHAIN_SHEET = "offchain asset location"
CURRENCIES_SHEET = "Currencies"

EVENT_TAG = "[REPACKAGING SETTLEMENT EVENT]"
PROCESSED_MARKER = "PROCESSED:REPACKAGING_SETTLEMENT"


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
    raise SystemExit("google_credentials.json not found.")


def _gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials as SACreds
    creds = SACreds.from_service_account_file(
        str(_find_google_credentials()),
        scopes=("https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.readonly"),
    )
    return gspread.authorize(creds)


def _retry(fn, attempts=3, base_delay=1.0, warn_on_error: str | None = None):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(base_delay * (2 ** i))
    if warn_on_error:
        print(f"  WARN  {warn_on_error}: {last}")
        return None
    raise last


# ── Field extraction from event text ──────────────────────────────────────

def _extract_field(text: str, label: str) -> str | None:
    m = re.search(rf"(?im)^-\s*{re.escape(label)}:\s*(.+)$", text)
    return m.group(1).strip() if m else None


# ── Telegram Chat Log scanning ────────────────────────────────────────────

def _find_unprocessed_settlements(gc) -> list[dict]:
    """Find Telegram Chat Log rows with [REPACKAGING SETTLEMENT EVENT] not yet
    marked as processed. Returns list of {row_idx, text, labels}."""
    sh = _retry(lambda: gc.open_by_key(TELEGRAM_SPREADSHEET_ID))
    ws = _retry(lambda: sh.worksheet(TELEGRAM_SHEET))
    data = _retry(lambda: ws.get_all_values())

    results = []
    for i, row in enumerate(data):
        row_idx = i + 1  # 1-based
        if row_idx <= 2:
            continue  # skip headers

        # col G is index 6 (0-based)
        text = row[6] if len(row) > 6 else ""
        if EVENT_TAG not in text:
            continue

        # Check if already processed (marker in col Q or R)
        col_q = row[16] if len(row) > 16 else ""
        col_r = row[17] if len(row) > 17 else ""
        if PROCESSED_MARKER in col_q or PROCESSED_MARKER in col_r:
            continue

        labels = {}
        for label in [
            "Composition URL", "Holder Name", "Farm Name", "State",
            "Country", "Year", "Landing Page", "Ledger URL",
            "SKU Mapping", "Deplete Inputs", "Add Output Locations",
            "Set Currencies Metadata", "Rebuild Inventory",
        ]:
            val = _extract_field(text, label)
            if val is not None:
                labels[label] = val

        results.append({"row_idx": row_idx, "text": text, "labels": labels})

    return results


def _mark_processed(gc, row_idx: int):
    """Write PROCESSED marker to col R (External API call response) of the row."""
    sh = _retry(lambda: gc.open_by_key(TELEGRAM_SPREADSHEET_ID))
    ws = _retry(lambda: sh.worksheet(TELEGRAM_SHEET))
    _retry(lambda: ws.update_cell(row_idx, 18, PROCESSED_MARKER))  # col R = 18


# ── Composition JSON ──────────────────────────────────────────────────────

def _fetch_composition(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ── Sheet operations ──────────────────────────────────────────────────────

def _deplete_inputs(gc, composition: dict, holder_name: str, dry_run: bool):
    """For each holder-inventory input, reduce or zero out its offchain amount."""
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    ws = _retry(lambda: sh.worksheet(OFFCHAIN_SHEET))
    data = _retry(lambda: ws.get_all_values())

    for inp in composition.get("inputs", []):
        if inp.get("line_kind") != "from_holder_inventory":
            continue
        currency = inp["currency"]
        quantity = inp["quantity"]

        found = None
        for i, row in enumerate(data):
            if i == 0:
                continue
            col_a = row[0].strip() if row else ""
            col_b = row[1].strip() if len(row) > 1 else ""
            if col_a == currency and col_b.lower() == holder_name.lower():
                found = i + 1
                break

        if found is None:
            print(f"  SKIP  {currency!r} — not found under {holder_name!r}")
            continue

        current = 0.0
        try:
            current = float(str(data[found - 1][2] if len(data[found - 1]) > 2 else "0"))
        except (ValueError, IndexError):
            pass

        new_amount = max(0.0, current - quantity)
        action = "DEPLETE" if new_amount == 0 else "REDUCE"
        print(f"  {action} {currency!r}: {current} → {new_amount} (consumed {quantity})")

        if not dry_run:
            _retry(lambda: ws.update_cell(found, 3, str(new_amount)),
                   warn_on_error=f"cannot write to offchain asset location row {found} (protected cell)")


def _add_output_locations(gc, composition: dict, holder_name: str, dry_run: bool):
    """Append new rows to offchain asset location for each output."""
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    ws = _retry(lambda: sh.worksheet(OFFCHAIN_SHEET))
    data = _retry(lambda: ws.get_all_values())

    # collect existing (currency, location) pairs
    existing = set()
    for row in data[1:]:
        if row:
            existing.add((row[0].strip() if row else "", (row[1].strip() if len(row) > 1 else "")))

    for out in composition.get("outputs", []):
        currency = out["suggested_currency"]
        units = out["units"]
        cost = out.get("unit_cost_usd", 0)
        total = out.get("line_total_usd", 0)

        if (currency, holder_name) in existing:
            print(f"  SKIP  {currency!r} — already exists under {holder_name!r}")
            continue

        print(f"  ADD   {currency!r} x{units} @ ${cost:.2f} (total ${total:.2f})")
        if not dry_run:
            _retry(lambda: ws.append_row([currency, holder_name, str(units), str(cost), str(total)]))


def _resolve_sku(suggested_currency: str, sku_mapping: dict | None) -> str | None:
    if not sku_mapping:
        return None
    for key, val in sku_mapping.items():
        if key in suggested_currency:
            return val
    return None


def _set_currencies_metadata(gc, composition: dict, labels: dict, dry_run: bool):
    """Update Currencies tab columns C, E-J, M for each output currency."""
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    ws = _retry(lambda: sh.worksheet(CURRENCIES_SHEET))
    data = _retry(lambda: ws.get_all_values())

    sku_json = labels.get("SKU Mapping", "")
    sku_mapping = None
    if sku_json:
        try:
            sku_mapping = json.loads(sku_json)
        except json.JSONDecodeError:
            print(f"  WARN  invalid SKU Mapping JSON: {sku_json[:100]!r}")

    for out in composition.get("outputs", []):
        currency = out["suggested_currency"]

        found = None
        for i, row in enumerate(data):
            if i == 0:
                continue
            if row and row[0].strip() == currency:
                found = i + 1
                break

        if found is None:
            print(f"  WARN  currency row not found: {currency!r}")
            continue

        updates = {}
        # col C (3) — isSerializable
        current_c = data[found - 1][2] if len(data[found - 1]) > 2 else ""
        if not current_c or str(current_c).strip().upper() != "TRUE":
            updates[3] = "TRUE"

        # col E (5) — landing_page
        if labels.get("Landing Page"):
            updates[5] = labels["Landing Page"]
        # col F (6) — ledger URL
        if labels.get("Ledger URL"):
            updates[6] = labels["Ledger URL"]
        # col G (7) — farm name
        if labels.get("Farm Name"):
            updates[7] = labels["Farm Name"]
        # col H (8) — state
        if labels.get("State"):
            updates[8] = labels["State"]
        # col I (9) — country
        if labels.get("Country"):
            updates[9] = labels["Country"]
        # col J (10) — year
        if labels.get("Year"):
            updates[10] = labels["Year"]
        # col M (13) — SKU Product ID
        sku = _resolve_sku(currency, sku_mapping)
        if sku:
            updates[13] = sku

        if not updates:
            print(f"  SKIP  {currency!r} — all metadata already set")
            continue

        cols = ",".join(f"col{c}" for c in sorted(updates))
        print(f"  SET   {currency!r} → {cols}")
        if not dry_run:
            for col_idx, value in updates.items():
                _retry(lambda c=col_idx, v=value: ws.update_cell(found, c, v))


def _rebuild_inventory(dry_run: bool):
    """Invoke sync_agroverse_store_inventory.py as subprocess."""
    script = REPO_ROOT.parent / "market_research" / "scripts" / "sync_agroverse_store_inventory.py"
    if not script.is_file():
        print(f"  WARN  inventory sync script not found: {script}")
        return
    print(f"  RUN   {script}")
    if not dry_run:
        import subprocess
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR inventory sync failed (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
        else:
            print(f"  OK    inventory snapshot rebuilt")


# ── Main ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Process [REPACKAGING SETTLEMENT EVENT] from Telegram Chat Logs")
    p.add_argument("--process-all", action="store_true", help="Process ALL unprocessed settlement events")
    p.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    p.add_argument("--no-rebuild", action="store_true", help="Skip inventory snapshot rebuild")
    p.add_argument("--skip-deplete", action="store_true", help="Skip input depletion step")
    p.add_argument("--skip-add-locations", action="store_true", help="Skip adding output locations step")
    p.add_argument("--skip-metadata", action="store_true", help="Skip Currencies metadata step")
    args = p.parse_args(argv)

    DRY = args.dry_run
    if DRY:
        print("DRY RUN — no writes will be made\n")

    gc = _gspread_client()
    settlements = _find_unprocessed_settlements(gc)

    if not settlements:
        print("No unprocessed [REPACKAGING SETTLEMENT EVENT] entries found.")
        return 0

    if not args.process_all and len(settlements) > 1:
        print(f"Found {len(settlements)} unprocessed entries. Use --process-all to process all.")
        print("Processing only the MOST RECENT one.\n")
        settlements = [settlements[-1]]

    for s in settlements:
        labels = s["labels"]
        composition_url = labels.get("Composition URL")
        holder_name = labels.get("Holder Name")

        if not composition_url or not holder_name:
            print(f"SKIP row {s['row_idx']}: missing Composition URL or Holder Name")
            continue

        print(f"=== Row {s['row_idx']} ===")
        print(f"Composition URL: {composition_url}")
        print(f"Holder Name: {holder_name}")

        # Fetch composition JSON
        try:
            composition = _fetch_composition(composition_url)
            print(f"Fetched composition: {len(composition.get('inputs', []))} inputs, {len(composition.get('outputs', []))} outputs")
        except Exception as e:
            print(f"ERROR fetching composition: {e}")
            continue

        # Step 1: Deplete inputs
        if args.skip_deplete:
            print("\n[1/4] DEPLETE INPUTS — skipped (--skip-deplete)")
        elif labels.get("Deplete Inputs", "true").lower() != "false":
            print("\n[1/4] DEPLETE INPUTS")
            _deplete_inputs(gc, composition, holder_name, DRY)
        else:
            print("\n[1/4] DEPLETE INPUTS — skipped (Deplete Inputs=false)")

        # Step 2: Add output locations
        if args.skip_add_locations:
            print("\n[2/4] ADD OUTPUT LOCATIONS — skipped (--skip-add-locations)")
        elif labels.get("Add Output Locations", "true").lower() != "false":
            print("\n[2/4] ADD OUTPUT LOCATIONS")
            _add_output_locations(gc, composition, holder_name, DRY)
        else:
            print("\n[2/4] ADD OUTPUT LOCATIONS — skipped")

        # Step 3: Set Currencies metadata
        if args.skip_metadata:
            print("\n[3/4] SET CURRENCIES METADATA — skipped (--skip-metadata)")
        elif labels.get("Set Currencies Metadata", "true").lower() != "false":
            print("\n[3/4] SET CURRENCIES METADATA")
            _set_currencies_metadata(gc, composition, labels, DRY)
        else:
            print("\n[3/4] SET CURRENCIES METADATA — skipped")

        # Step 4: Rebuild inventory snapshot
        rebuild = labels.get("Rebuild Inventory", "false").lower()
        if rebuild == "true" and not args.no_rebuild:
            print("\n[4/4] REBUILD INVENTORY SNAPSHOT")
            _rebuild_inventory(DRY)
        else:
            print("\n[4/4] REBUILD INVENTORY SNAPSHOT — skipped")

        # Mark as processed
        if not DRY:
            _mark_processed(gc, s["row_idx"])
            print(f"\nMarked row {s['row_idx']} as processed.")
        else:
            print(f"\n[DRY RUN] Would mark row {s['row_idx']} as processed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
