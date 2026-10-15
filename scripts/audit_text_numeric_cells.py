"""Detect (and optionally repair) text-typed cells in numeric ledger columns.

Why: derived views use `sum(col)`, which silently DROPS text-typed cells. A signed row
whose quantity/amount landed as text therefore vanishes from the aggregate (real incident
2026-10-15, Unit D thermic-box reclass: rows r4931/r4932 stored D as text `"2.00000000"`,
so the `offchain asset location` view ignored them and the item was dropped).

This scans a sheet column and reports cells whose value is a numeric string but which the
Sheets API returns as text. `--repair` rewrites them via USER_ENTERED so they become true
numbers. Read-only by default.

Usage:
    python3 scripts/audit_text_numeric_cells.py --sheet "offchain transactions" --col D
    python3 scripts/audit_text_numeric_cells.py --sheet "offchain transactions" --col D --repair
"""

from __future__ import annotations

import argparse
import sys

from truesight_dao_client.server.config import get_settings
from truesight_dao_client.server.sheets import base

MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"


def scan(col: str, sheet: str, spreadsheet_id: str) -> list[tuple[int, str]]:
    """Return (row_number, raw_string) for cells that are numeric-looking strings."""
    rows = base.get_values(
        spreadsheet_id,
        f"{base.quoted_prefix(sheet)}!{col}2:{col}",
        key_path=get_settings().google_sa_json,
    )
    hits: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        if not row:
            continue
        val = row[0]
        # get_values returns strings for both text and (formatted) numbers; a value that
        # coerce_numeric changes is by definition text-typed in the API response.
        if isinstance(val, str) and base.coerce_numeric(val) != val:
            hits.append((i + 2, val))
    return hits


def repair(col: str, sheet: str, spreadsheet_id: str, hits: list[tuple[int, str]]) -> int:
    fixed = 0
    for row_number, raw in hits:
        base.update_cell(
            spreadsheet_id,
            f"{base.quoted_prefix(sheet)}!{col}{row_number}",
            base.coerce_numeric(raw),
            key_path=get_settings().google_sa_json,
        )
        fixed += 1
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default="offchain transactions")
    ap.add_argument("--col", default="D")
    ap.add_argument("--spreadsheet-id", default=MAIN_LEDGER_ID)
    ap.add_argument("--repair", action="store_true", help="rewrite the offending cells as numbers")
    args = ap.parse_args()

    hits = scan(args.col, args.sheet, args.spreadsheet_id)
    if not hits:
        print(f"OK: no text-typed numeric cells in {args.sheet}!{args.col}")
        return 0
    print(f"FOUND {len(hits)} text-typed numeric cell(s) in {args.sheet}!{args.col}:")
    for row_number, raw in hits[:50]:
        print(f"  row {row_number}: {raw!r}")
    if args.repair:
        print(f"repairing {len(hits)} cell(s)…")
        print(f"repaired {repair(args.col, args.sheet, args.spreadsheet_id, hits)} cell(s)")
    else:
        print("(read-only; pass --repair to fix)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
