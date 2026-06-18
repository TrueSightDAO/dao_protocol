#!/usr/bin/env python3
"""Submit [CAPITAL INJECTION EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_capital_injection.html

Capital Injection is **managed-AGL-only** — the GAS rejects offchain
submissions (validateManagedLedger). Hence `Ledger URL` uses the strict
`google_sheets_url` validator (non-empty + correct shape) rather than
the looser `_or_empty` variant Currency Conversion uses.

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_capital_injection --help
"""
import sys

from ..edgar_client import build_event_cli
from ..validators import (
    google_sheets_url,
    ledger_name,
    normalize_number,
    positive_number,
    required,
)

main = build_event_cli(
    event_name='CAPITAL INJECTION EVENT',
    canonical_labels=['Ledger', 'Ledger URL', 'Amount', 'Description', 'Attached Filename', 'Destination Capital Injection File Location'],
    dapp_page='report_capital_injection.html',
    validators={
        'Ledger': ledger_name,
        'Ledger URL': google_sheets_url,
        'Amount': positive_number,
        'Description': required,
    },
    normalizers={
        'Amount': normalize_number,
    },
)

if __name__ == "__main__":
    sys.exit(main())
