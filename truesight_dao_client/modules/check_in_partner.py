#!/usr/bin/env python3
"""Submit ``[PARTNER CHECK-IN EVENT]`` to log a periodic partner check-in.

Routes through the canonical async pattern (DApp / dao_client signs → Edgar
``/dao/submit_contribution`` → Telegram Chat Logs → ``WebhookTriggerWorker``
fires the ``processPartnerCheckInsFromTelegramChatLogs`` GAS scanner →
appends row to **Partner Check-ins** tab on the Main Ledger).

Use cases:
  - Log a check-in from the terminal after texting a partner.
  - Batch-log check-ins from a phone call session.
  - Backfill missed check-ins with accurate dates.

Required:
  - ``./.env`` with EMAIL, PUBLIC_KEY, PRIVATE_KEY (run ``truesight-dao-auth login``).
  - ``--partner-id`` (must match an `Agroverse Partners` row).
  - ``--contributor-name`` (must match `Contributors contact information`!A).

Run:
  python -m truesight_dao_client.modules.check_in_partner --help

Convention:
  https://github.com/TrueSightDAO/agentic_ai_context/blob/main/PARTNER_CHECK_IN_IMPLEMENTATION.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import secrets
import sys

from ..edgar_client import EdgarClient

DEFAULT_GEN = (
    "https://github.com/TrueSightDAO/agentic_ai_context/blob/main/PARTNER_CHECK_IN_IMPLEMENTATION.md"
)
EVENT_NAME = "PARTNER CHECK-IN EVENT"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Submit [PARTNER CHECK-IN EVENT] (signed) to log a periodic "
            "partner check-in via Edgar + GAS scanner."
        ),
    )
    p.add_argument("--partner-id", required=True, help="Slug from Agroverse Partners!A (e.g. the-way-home-shop).")
    p.add_argument("--contributor-name", required=True, help="Exact Contributors contact information!A name (e.g. 'Gergana - The Way Home Shop').")
    p.add_argument("--check-in-date", default="", help="ISO date YYYY-MM-DD. Default: today.")
    p.add_argument("--method", required=True, choices=["Text", "Phone", "In Person", "Email", "Other"], help="How the check-in was conducted.")
    p.add_argument("--stock-status", required=True, choices=["Low", "Out", "OK", "Unknown"], help="Partner's current stock status.")
    p.add_argument("--restock-needed", required=True, choices=["Yes", "No", "Maybe"], help="Whether partner needs a restock.")
    p.add_argument("--restock-sku", default="", help="SKU slug from partners-velocity.json items (e.g. 8-ounce-organic-cacao-nibs). Use 'Other' if the partner asked for a SKU they don't carry. Only meaningful when --restock-needed=Yes.")
    p.add_argument("--restock-quantity", default="", help="Integer quantity (units of --restock-sku). Only meaningful when --restock-needed=Yes.")
    p.add_argument("--next-check-in-date", default="", help="ISO date YYYY-MM-DD. When to check in again.")
    p.add_argument("--notes", default="", help="Free-form remark.")
    p.add_argument(
        "--update-id",
        default="",
        help="Optional explicit Update ID. Default: PCI_<14-digit timestamp>.",
    )
    p.add_argument(
        "--generation-source",
        default=DEFAULT_GEN,
        help="`This submission was generated using …` link.",
    )
    p.add_argument("--dry-run", action="store_true", help="Print signed share text; do not POST to Edgar.")

    args = p.parse_args(argv)

    check_in_date = args.check_in_date.strip()
    if not check_in_date:
        check_in_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    update_id = args.update_id.strip()
    if not update_id:
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(3)
        update_id = f"PCI_{ts}_{suffix}"

    client = EdgarClient.from_env()
    client.generation_source = args.generation_source.strip()

    attrs: list[tuple[str, str]] = []

    def _add(label: str, value: str) -> None:
        v = (value or "").strip()
        if v:
            attrs.append((label, v))

    _add("Partner ID", args.partner_id)
    _add("Contributor Name", args.contributor_name)
    _add("Check-in Date", check_in_date)
    _add("Method", args.method)
    _add("Stock Status", args.stock_status)
    _add("Restock Needed", args.restock_needed)
    _add("Restock SKU", args.restock_sku)
    _add("Restock Quantity", args.restock_quantity)
    _add("Next Check-in Date", args.next_check_in_date)
    _add("Notes", args.notes)
    _add("Update ID", update_id)

    if args.dry_run:
        payload, txn_id, share_text = client.sign(EVENT_NAME, attrs)
        print(share_text)
        return 0

    resp = client.submit(EVENT_NAME, attrs)
    body = resp.text
    print(f"HTTP {resp.status_code}")
    print(body)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    sys.exit(main())
