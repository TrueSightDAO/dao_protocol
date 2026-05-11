#!/usr/bin/env python3
"""Submit [DAO Inventory Expense Event] to Edgar.

Browser equivalent: dapp.truesight.me/report_dao_expenses.html

`Target Ledger` accepts either a managed AGL name (e.g. "AGL16") OR the literal
string "offchain" — the receiving GAS dispatches by name, not URL, for expenses.
That's why no URL validator is wired here. Lat/Lng allowed empty for events
without geolocation. Inventory Quantity is positive (expenses get negated to
asset-reduction sign in the GAS, not here).

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_dao_expenses --help
"""
import sys

from ..edgar_client import build_event_cli
from ..validators import (
    latitude,
    longitude,
    normalize_number,
    positive_number,
    required,
)

main = build_event_cli(
    event_name='DAO Inventory Expense Event',
    canonical_labels=['DAO Member Name', 'Target Ledger', 'Latitude', 'Longitude', 'Inventory Type', 'Inventory Quantity', 'Description', 'Attached Filename', 'Destination Expense File Location', 'Submission Source'],
    dapp_page='report_dao_expenses.html',
    validators={
        'DAO Member Name': required,
        'Target Ledger': required,
        'Latitude': latitude,
        'Longitude': longitude,
        'Inventory Type': required,
        'Inventory Quantity': positive_number,
        'Description': required,
    },
    normalizers={
        'Inventory Quantity': normalize_number,
        'Latitude': normalize_number,
        'Longitude': normalize_number,
    },
)

if __name__ == "__main__":
    sys.exit(main())
