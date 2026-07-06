#!/usr/bin/env python3
"""Submit [QR CODE UPDATE EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/update_qr_code.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.update_qr_code --help

Named flags (each maps to the exact label the GAS parser expects):

    --qr-code VALUE         (label: QR Code)
    --associated-member VALUE  (label: Associated Member — note the 'd')
    --new-status VALUE      (label: New Status)
    --new-email VALUE       (label: New Email)
    --stripe-session-id VALUE  (label: Stripe Session ID)
    --shipping-provider VALUE  (label: Shipping Provider)
    --tracking-number VALUE   (label: Tracking Number)

The --attr escape hatch also works.
"""
import sys

from ..edgar_client import build_event_cli

main = build_event_cli(
    event_name='QR CODE UPDATE EVENT',
    canonical_labels=[
        'QR Code',
        'Associated Member',
        'New Status',
        'New Email',
        'Stripe Session ID',
        'Shipping Provider',
        'Tracking Number',
    ],
    dapp_page='update_qr_code.html',
)

if __name__ == "__main__":
    sys.exit(main())
