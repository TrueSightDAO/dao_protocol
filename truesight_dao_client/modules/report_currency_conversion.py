#!/usr/bin/env python3
"""Submit [CURRENCY CONVERSION EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/currency_conversion.html

Runs the same end-to-end flow:
  - signed [CURRENCY CONVERSION EVENT] payload POSTed to Edgar
  - Edgar logs to Telegram Chat Logs col G + fires the GAS webhook
  - GAS routes to Main Ledger `offchain transactions` (when no Ledger URL)
    or to the matched managed AGL ledger's `Transactions` tab

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_currency_conversion --help

Typical use:
    # Offchain (Main Ledger): USD -> BRL via Wise, no managed-ledger URL.
    python -m truesight_dao_client.modules.report_currency_conversion \\
        --warehouse-manager 'Gary Teh' \\
        --source-currency USD --source-amount 1000 \\
        --target-currency 'Brazilian Reis' --target-amount 4985 \\
        --description 'Wise transfer USD->BRL to Rendimento for May payout' \\
        --attachment ~/Downloads/wise_receipt.pdf

    # Managed AGL ledger (e.g. TRIBO_MIRIM_BAHIA): include both Ledger + Ledger URL.
    python -m truesight_dao_client.modules.report_currency_conversion \\
        --ledger TRIBO_MIRIM_BAHIA \\
        --ledger-url 'https://docs.google.com/spreadsheets/d/.../edit' \\
        --warehouse-manager 'Gary Teh' \\
        --source-currency USD --source-amount 100 \\
        --target-currency 'Brazilian Reis' --target-amount 510 \\
        --description 'Stripe donation FX'
"""
from __future__ import annotations

import datetime
import sys

from ..edgar_client import build_event_cli
from ..validators import (
    currency_code,
    google_sheets_url_or_empty,
    normalize_currency,
    normalize_date_to_yyyymmdd,
    normalize_number,
    positive_number,
    required,
    yyyymmdd_date,
)

# Canonical label list — MUST stay in sync with the GAS parser
# (`parseCurrencyConversionMessage` in tokenomics' currency_conversion_processing.gs)
# AND the DApp page (currency_conversion.html submitReport).
#
# Order here is the order they appear in the signed payload, so the human-readable
# Telegram log matches what the DApp emits. If the GAS later requires a new label,
# add it here AND on the DApp side AND in the GAS regex; --dry-run will reveal drift.
LABELS = [
    'Ledger',
    'Ledger URL',
    'Warehouse Manager',
    'Source Currency',
    'Source Amount',
    'Target Currency',
    'Target Amount',
    'Implied Rate',
    'Conversion Date',
    'Description',
    'Attached Filename',
    'Destination Currency Conversion File Location',
]

VALIDATORS = {
    'Ledger': required,
    # Ledger URL intentionally NOT in `required` — empty URL means "offchain (Main Ledger)".
    # google_sheets_url_or_empty enforces shape when present.
    'Ledger URL': google_sheets_url_or_empty,
    'Warehouse Manager': required,
    'Source Currency': currency_code,
    'Source Amount': positive_number,
    'Target Currency': currency_code,
    'Target Amount': positive_number,
    'Conversion Date': yyyymmdd_date,
    'Description': required,
}

NORMALIZERS = {
    'Source Currency': normalize_currency,
    'Target Currency': normalize_currency,
    'Source Amount': normalize_number,
    'Target Amount': normalize_number,
    'Conversion Date': normalize_date_to_yyyymmdd,
}


def _today_yyyymmdd() -> str:
    return datetime.date.today().strftime("%Y%m%d")


def main(argv: list[str] | None = None) -> int:
    # build_event_cli treats every label as optional; we layer two CLI ergonomics
    # over its argparse:
    #   1. Default --conversion-date to today (matching the DApp behavior).
    #   2. Default --ledger to "offchain" (matching the DApp's default option).
    #   3. Auto-fill --implied-rate from source/target if both provided and rate omitted.
    # We do this by mutating argv before delegating.
    argv = list(argv) if argv is not None else sys.argv[1:]

    def has_flag(flag: str) -> bool:
        return any(a == flag or a.startswith(flag + "=") for a in argv)

    if not has_flag("--conversion-date"):
        argv += ["--conversion-date", _today_yyyymmdd()]

    if not has_flag("--ledger"):
        argv += ["--ledger", "offchain"]

    if (
        not has_flag("--implied-rate")
        and has_flag("--source-amount")
        and has_flag("--target-amount")
        and has_flag("--source-currency")
        and has_flag("--target-currency")
    ):
        # Pull the four values out of argv (handles both "--flag=val" and "--flag val")
        def value_of(flag: str) -> str | None:
            for i, a in enumerate(argv):
                if a == flag and i + 1 < len(argv):
                    return argv[i + 1]
                if a.startswith(flag + "="):
                    return a.split("=", 1)[1]
            return None
        try:
            sa = float(str(value_of("--source-amount")).replace(",", ""))
            ta = float(str(value_of("--target-amount")).replace(",", ""))
            if sa > 0 and ta > 0:
                rate = round(ta / sa, 6)
                # Use the same normalization as the currency fields themselves so
                # the rate display reads cleanly for both ISO codes and
                # descriptive names ("1 USD = 4.985 Brazilian Reis").
                src_disp = normalize_currency(value_of("--source-currency"))
                tgt_disp = normalize_currency(value_of("--target-currency"))
                argv += [
                    "--implied-rate",
                    f"1 {src_disp} = {rate} {tgt_disp}",
                ]
        except (TypeError, ValueError):
            pass  # let the validators report the real problem

    inner = build_event_cli(
        event_name='CURRENCY CONVERSION EVENT',
        canonical_labels=LABELS,
        dapp_page='currency_conversion.html',
        validators=VALIDATORS,
        normalizers=NORMALIZERS,
    )
    return inner(argv)


if __name__ == "__main__":
    sys.exit(main())
