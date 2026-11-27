#!/usr/bin/env python3
"""Repoint Agroverse QR code rows: Manager Name (col U) and/or Currency (col I).

Repointing a batch used to require a hand-rolled `gspread` script plus a
manually-saved `PRE_WRITE_*` snapshot. This module makes it a first-class,
dry-run-first, snapshot-always CLI so the operation is repeatable and auditable.

It writes **the Google Sheet only** -- it does NOT submit any event to Edgar.
A repoint is a correction of a mis-booked row, not a custody transfer; if the
underlying stock genuinely moved between holders use
`truesight-dao-report-inventory-movement` instead.

Typical use (the case that prompted it): a batch of finished cacao QR codes was
stamped with the *origin* SKU and the origin holder, while the goods had already
arrived. Repoint them at the arrived (AWB-suffixed) SKU and at the holder who
actually has them:

    # 1. always look first
    truesight-dao-repoint-qr-codes \
        --qr 2024PAULO_20251018 --qr 2024PAULO_20251019 \
        --manager "Kirsten Ritschel" \
        --currency "Ceremonial Cacao Kraft Pouch - 20250219006 | Cacao Mass | 200 grams | Paulo 2024 | Santos 018-2025 016-2025 || Ilheus - AGL8 + 047-3175-3223 - San Francisco" \
        --dry-run

    # 2. apply once the plan looks right
    truesight-dao-repoint-qr-codes --qr-file codes.txt --manager "Kirsten Ritschel" --apply

Safety properties, all deliberate:

* **Dry-run is the default.** Nothing is written without `--apply`.
* **Snapshot before write.** Every touched row is dumped to
  `PRE_WRITE_repoint_qr_<ts>.json` in `--snapshot-dir` (default `~/creds`),
  so the change is reversible by hand even if the process dies mid-way.
* **Refuses to touch sold rows** unless `--allow-sold`. A SOLD QR has an owner
  and a sale event behind it; silently re-pointing it corrupts the audit trail.
* **Validates before writing.** The target manager must already exist in
  `Contributors contact information`, and the target currency in `Currencies`.
  This prevents the two failure modes seen in practice: a near-miss name that
  spawns a duplicate contributor row, and a hand-typed SKU with a typo in a
  130-character string.
* **Verifies after write.** Re-reads the affected cells and exits non-zero on
  any mismatch.

Per OPERATING_INSTRUCTIONS.md §5j, resolve *what a SKU is* with
`describe_sku.py` before repointing: a component (blank `Serializable`) must
never become a QR target.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..server.sheets import base

SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
QR_SHEET = "Agroverse QR codes"
CONTRIBUTORS_SHEET = "Contributors contact information"
CURRENCIES_SHEET = "Currencies"

# 1-based column indices, per SCHEMA.md (see server/sheets/qr_codes.py).
COL_QR_CODE = 1  # A
COL_STATUS = 2  # B
COL_SKU = 9  # I = Currency
COL_MANAGER = 21  # U = Manager Name (header contains a line break)

# Statuses that must not be silently repointed (a sale/custody event exists).
LOCKED_STATUSES = {"sold", "scanned / sold", "redeemed", "consumed"}


@dataclass
class QrRow:
    """One QR row as read from the sheet."""

    row: int
    qr_code: str
    currency: str = ""
    manager: str = ""
    status: str = ""


@dataclass
class Change:
    row: int
    col: int
    col_letter: str
    qr_code: str
    old: str
    new: str

    @property
    def field_name(self) -> str:
        return "Manager Name" if self.col == COL_MANAGER else "Currency"


@dataclass
class Plan:
    """Outcome of planning a repoint. Pure data -- no I/O."""

    changes: list[Change] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unchanged: int = 0
    requested: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def touched_rows(self) -> list[int]:
        return sorted({c.row for c in self.changes})


def _letter(col: int) -> str:
    """1-based column index -> spreadsheet letter (1->A, 21->U)."""
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def plan_repoint(
    rows: list[QrRow],
    *,
    new_manager: str | None = None,
    new_currency: str | None = None,
    known_managers: set[str] | None = None,
    known_currencies: set[str] | None = None,
    allow_sold: bool = False,
) -> Plan:
    """Decide which cells to write. Pure function -- no network, no writes.

    ``known_managers`` / ``known_currencies`` are the authoritative sets the
    targets are validated against; pass ``None`` to skip that validation (the
    CLI always supplies them).
    """
    plan = Plan(requested=len(rows))

    if not rows:
        plan.errors.append("No QR codes matched; nothing to do.")
        return plan
    if new_manager is None and new_currency is None:
        plan.errors.append("Nothing to change: pass --manager and/or --currency.")
        return plan

    for name, value in (("manager", new_manager), ("currency", new_currency)):
        if value is not None:
            if not value.strip():
                plan.errors.append(f"Empty --{name} value.")
            elif value != value.strip():
                plan.errors.append(
                    f"--{name} has leading/trailing whitespace: {value!r}"
                )

    if (
        new_manager is not None
        and known_managers is not None
        and new_manager not in known_managers
    ):
        close = _near_miss(new_manager, known_managers)
        hint = f" Did you mean {close!r}?" if close else ""
        plan.errors.append(
            f"Manager {new_manager!r} is not in {CONTRIBUTORS_SHEET}!A. "
            f"Writing it would create a duplicate contributor row.{hint}"
        )
    if (
        new_currency is not None
        and known_currencies is not None
        and new_currency not in known_currencies
    ):
        close = _near_miss(new_currency, known_currencies)
        hint = f" Closest: {close!r}." if close else ""
        plan.errors.append(
            f"Currency {new_currency!r} is not in {CURRENCIES_SHEET}!A.{hint}"
        )

    if not plan.ok:
        return plan

    # Phase A: per-row guards. Collect every problem BEFORE planning any change,
    # so a single bad row aborts the whole batch rather than repointing the rest
    # partially (a partial repoint is worse than none -- it splits a batch).
    for r in rows:
        if (r.status or "").strip().lower() in LOCKED_STATUSES and not allow_sold:
            plan.errors.append(
                f"{r.qr_code} (row {r.row}) has status {r.status!r}. "
                f"Refusing to repoint a settled row; pass --allow-sold to override."
            )
    if not plan.ok:
        return plan

    # Phase B: build changes. Only reached when the whole batch is clean.
    for r in rows:
        if new_manager is not None and r.manager != new_manager:
            plan.changes.append(
                Change(
                    r.row,
                    COL_MANAGER,
                    _letter(COL_MANAGER),
                    r.qr_code,
                    r.manager,
                    new_manager,
                )
            )
        if new_currency is not None and r.currency != new_currency:
            plan.changes.append(
                Change(
                    r.row,
                    COL_SKU,
                    _letter(COL_SKU),
                    r.qr_code,
                    r.currency,
                    new_currency,
                )
            )
        if (new_manager is None or r.manager == new_manager) and (
            new_currency is None or r.currency == new_currency
        ):
            plan.unchanged += 1

    if plan.ok and not plan.changes:
        plan.warnings.append("All matching rows already have the requested values.")

    dupes = _duplicate_codes(rows)
    if dupes:
        plan.warnings.append(f"Duplicate QR codes in sheet rows: {sorted(dupes)}")

    return plan


def _duplicate_codes(rows: list[QrRow]) -> dict[str, list[int]]:
    seen: dict[str, list[int]] = {}
    for r in rows:
        seen.setdefault(r.qr_code, []).append(r.row)
    return {k: v for k, v in seen.items() if len(v) > 1}


def _near_miss(value: str, candidates: set[str]) -> str | None:
    """Typo hint: case-insensitive exact, then prefix, then fuzzy similarity.

    The fuzzy step matters: a transposed-letter typo ("Ritshel" for "Ritschel")
    is not a prefix match, and it is precisely the case that silently creates a
    duplicate contributor row.
    """
    low = value.strip().lower()
    for c in candidates:
        if c.strip().lower() == low:
            return c
    for c in sorted(candidates):
        if c.strip().lower().startswith(low) or low.startswith(c.strip().lower()):
            return c
    close = difflib.get_close_matches(
        value.strip(), sorted(candidates), n=1, cutoff=0.75
    )
    return close[0] if close else None


# --------------------------------------------------------------------------- #
# I/O layer
# --------------------------------------------------------------------------- #
def _key_path() -> str | None:
    from ..config import get_settings

    return get_settings().google_sa_json_qr_lookup


def fetch_rows(qr_codes: list[str]) -> tuple[list[QrRow], list[str]]:
    """Read the QR sheet once and return (matched rows, missing codes)."""
    keys = base.get_values(
        SPREADSHEET_ID, f"{base.quoted_prefix(QR_SHEET)}!A:V", _key_path()
    )
    wanted = {q.strip() for q in qr_codes if q.strip()}
    rows: list[QrRow] = []
    found: set[str] = set()
    for idx, raw in enumerate(keys, start=1):
        code = base.cell(raw, COL_QR_CODE).strip()
        if code not in wanted:
            continue
        found.add(code)
        rows.append(
            QrRow(
                row=idx,
                qr_code=code,
                currency=base.cell(raw, COL_SKU).strip(),
                manager=base.cell(raw, COL_MANAGER).strip(),
                status=base.cell(raw, COL_STATUS).strip(),
            )
        )
    return rows, sorted(wanted - found)


def _column_values(sheet: str) -> set[str]:
    vals = base.get_values(
        SPREADSHEET_ID, f"{base.quoted_prefix(sheet)}!A:A", _key_path()
    )
    return {base.cell(r, 1).strip() for r in vals if base.cell(r, 1).strip()}


def write_snapshot(rows: list[QrRow], plan: Plan, snapshot_dir: str) -> str:
    """Persist every touched row verbatim before writing. Returns the path."""
    os.makedirs(snapshot_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(snapshot_dir, f"PRE_WRITE_repoint_qr_{ts}.json")
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "spreadsheet_id": SPREADSHEET_ID,
        "sheet": QR_SHEET,
        "rows": [
            {
                "row": r.row,
                "qr_code": r.qr_code,
                "currency": r.currency,
                "manager": r.manager,
                "status": r.status,
            }
            for r in rows
            if r.row in set(plan.touched_rows)
        ],
        "planned_changes": [
            {
                "row": c.row,
                "cell": f"{c.col_letter}{c.row}",
                "field": c.field_name,
                "old": c.old,
                "new": c.new,
            }
            for c in plan.changes
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def apply_plan(plan: Plan) -> dict:
    data = [
        {
            "range": (f"{base.quoted_prefix(QR_SHEET)}!{c.col_letter}{c.row}"),
            "values": [[c.new]],
        }
        for c in plan.changes
    ]
    return base.batch_update(SPREADSHEET_ID, data, _key_path())


def verify(plan: Plan) -> list[str]:
    """Re-read the touched cells and report any mismatch."""
    problems: list[str] = []
    for c in plan.changes:
        got = base.get_values(
            SPREADSHEET_ID,
            f"{base.quoted_prefix(QR_SHEET)}!{c.col_letter}{c.row}",
            _key_path(),
        )
        actual = base.cell(got[0], 1).strip() if got else ""
        if actual != c.new:
            problems.append(f"{c.col_letter}{c.row} expected {c.new!r} got {actual!r}")
    return problems


def _read_qr_args(args: argparse.Namespace) -> list[str]:
    codes: list[str] = list(args.qr or [])
    if args.qr_file:
        with open(args.qr_file, encoding="utf-8") as fh:
            for line in fh:
                code = line.split("#", 1)[0].strip()
                if code:
                    codes.append(code)
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Repoint Agroverse QR rows (Manager Name / Currency). "
            "Writes the sheet only; submits no Edgar event. Dry-run by default."
        )
    )
    p.add_argument(
        "--qr", action="append", metavar="CODE", help="QR code to repoint (repeatable)."
    )
    p.add_argument(
        "--qr-file",
        metavar="PATH",
        help="File of QR codes, one per line ('#' comments ok).",
    )
    p.add_argument(
        "--manager",
        metavar="NAME",
        help="New Manager Name (col U). Must exist in Contributors.",
    )
    p.add_argument(
        "--currency",
        metavar="SKU",
        help="New Currency / SKU (col I). Must exist in Currencies.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually write. Without this the run is a dry-run.",
    )
    p.add_argument(
        "--allow-sold",
        action="store_true",
        help="Permit repointing rows with a settled status.",
    )
    p.add_argument(
        "--snapshot-dir",
        default=os.path.expanduser("~/creds"),
        help="Where to write the PRE_WRITE_*.json snapshot.",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = p.parse_args(argv)

    codes = _read_qr_args(args)
    if not codes:
        print("Error: pass --qr and/or --qr-file.", file=sys.stderr)
        return 2
    if not args.manager and not args.currency:
        print("Error: pass --manager and/or --currency.", file=sys.stderr)
        return 2

    try:
        rows, missing = fetch_rows(codes)
        known_managers = _column_values(CONTRIBUTORS_SHEET) if args.manager else None
        known_currencies = _column_values(CURRENCIES_SHEET) if args.currency else None
    except Exception as exc:  # noqa: BLE001 - CLI must surface, not crash
        print(f"Sheet read failed: {exc}", file=sys.stderr)
        return 1

    plan = plan_repoint(
        rows,
        new_manager=args.manager,
        new_currency=args.currency,
        known_managers=known_managers,
        known_currencies=known_currencies,
        allow_sold=args.allow_sold,
    )
    if missing:
        plan.errors.append(f"QR code(s) not found on {QR_SHEET}: {missing}")

    if args.json:
        print(
            json.dumps(
                {
                    "ok": plan.ok,
                    "requested": plan.requested,
                    "changed": len(plan.changes),
                    "unchanged": plan.unchanged,
                    "errors": plan.errors,
                    "warnings": plan.warnings,
                    "changes": [
                        {
                            "cell": f"{c.col_letter}{c.row}",
                            "qr_code": c.qr_code,
                            "field": c.field_name,
                            "old": c.old,
                            "new": c.new,
                        }
                        for c in plan.changes
                    ],
                },
                indent=2,
            )
        )

    if not plan.ok:
        for e in plan.errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    for w in plan.warnings:
        print(f"WARN: {w}")
    if not plan.changes:
        print(f"No changes needed across {plan.requested} row(s).")
        return 0

    print(
        f"Plan: {len(plan.changes)} cell change(s) across "
        f"{len(plan.touched_rows)} row(s); {plan.unchanged} already correct."
    )
    for c in plan.changes[:40]:
        print(
            f"  {c.col_letter}{c.row} {c.qr_code} {c.field_name}: {c.old!r} -> {c.new!r}"
        )
    if len(plan.changes) > 40:
        print(f"  ... and {len(plan.changes) - 40} more")

    if not args.apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply to write.")
        return 0

    try:
        snap = write_snapshot(rows, plan, args.snapshot_dir)
    except OSError as exc:
        print(f"Snapshot failed, refusing to write: {exc}", file=sys.stderr)
        return 1
    print(f"Snapshot: {snap}")

    try:
        apply_plan(plan)
    except Exception as exc:  # noqa: BLE001 - CLI must surface, not crash
        print(f"WRITE FAILED after snapshot ({snap}): {exc}", file=sys.stderr)
        return 1

    problems = verify(plan)
    if problems:
        print("POST-WRITE VERIFY FAILED:", file=sys.stderr)
        for prob in problems:
            print(f"  {prob}", file=sys.stderr)
        return 1
    print(f"Verified {len(plan.changes)}/{len(plan.changes)} cell(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
