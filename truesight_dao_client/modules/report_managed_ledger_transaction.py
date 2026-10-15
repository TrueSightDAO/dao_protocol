#!/usr/bin/env python3
"""Submit a [MANAGED LEDGER TRANSACTION EVENT] to Edgar.

Records a signed, multi-row transaction against a managed AGL ledger (e.g.
moving USD between AGL15 (financier) and AGL8/AGL13), following the
one-signed-blob-many-rows precedent (AGL14 ledger rows 10-13).

Sibling of `report_capital_injection` / `report_dao_expenses` /
`report_asset_receipt`. `CAPITAL INJECTION EVENT` is documented as an
*external* investment; this module is the vehicle for *internal*
inter-ledger moves (Black King freight-lane plan 3-E2).

NOTE: `[MANAGED LEDGER TRANSACTION EVENT]` is not yet listed in Edgar's
events catalog (GET /events-catalog) -- the event is currently produced
only by the legacy GAS blob. This module is the client-side half; an
Edgar-side catalog/registration entry must accompany it before a live
submission will route. `--dry-run` prints the signed text without
submitting.

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_managed_ledger_transaction --help
    # or: truesight-dao-report-managed-ledger-transaction --help
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
    event_name="MANAGED LEDGER TRANSACTION EVENT",
    canonical_labels=[
        "Ledger",
        "Ledger URL",
        "Date",
        "Amount",
        "Currency",
        "Sender",
        "Recipient",
        "Description",
        "Attached Filename",
        "Destination Managed Ledger Transaction File Location",
    ],
    dapp_page=None,
    validators={
        "Ledger": ledger_name,
        "Ledger URL": google_sheets_url,
        "Amount": positive_number,
        "Sender": required,
        "Recipient": required,
        "Description": required,
    },
    normalizers={
        "Amount": normalize_number,
    },
)

if __name__ == "__main__":
    sys.exit(main())
