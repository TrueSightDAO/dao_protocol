#!/usr/bin/env python3
"""Submit [ASSET RECEIPT EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_asset_receipt.html

Run:
    python -m truesight_dao_client.modules.report_asset_receipt --help
    # or: truesight-dao-report-asset-receipt --help
"""
import sys

from ..edgar_client import build_event_cli

main = build_event_cli(
    event_name='ASSET RECEIPT EVENT',
    canonical_labels=['Currency', 'Amount', 'Description', 'Fund Handler', 'Attached Filename', 'Destination Contribution File Location'],
    dapp_page=None,
)

if __name__ == "__main__":
    sys.exit(main())
