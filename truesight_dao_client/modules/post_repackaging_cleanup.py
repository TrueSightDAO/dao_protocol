#!/usr/bin/env python3
"""Submit [REPACKAGING SETTLEMENT EVENT] to Edgar.

Populates offchain asset location + Currencies metadata after a repackaging
batch has been processed by the repackaging-currency-ingest GAS.

DApp equivalent: dapp.truesight.me/repackaging_settlement.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.post_repackaging_cleanup --help
"""
import sys

from ..edgar_client import build_event_cli
from ..validators import required, url_or_empty

main = build_event_cli(
    event_name='REPACKAGING SETTLEMENT EVENT',
    canonical_labels=[
        'Composition URL',
        'Holder Name',
        'Farm Name',
        'State',
        'Country',
        'Year',
        'Landing Page',
        'Ledger URL',
        'SKU Mapping',
        'Deplete Inputs',
        'Add Output Locations',
        'Set Currencies Metadata',
        'Rebuild Inventory',
        'Submission Source',
    ],
    required_labels=['Composition URL', 'Holder Name'],
    validators={
        'Composition URL': required,
        'Holder Name': required,
        'Landing Page': url_or_empty,
        'Ledger URL': url_or_empty,
    },
    defaults={
        'Deplete Inputs': 'true',
        'Add Output Locations': 'true',
        'Set Currencies Metadata': 'true',
        'Rebuild Inventory': 'false',
        'Submission Source': 'Repackaging Settlement CLI',
    },
    dapp_page='repackaging_settlement.html',
)

if __name__ == "__main__":
    sys.exit(main())
