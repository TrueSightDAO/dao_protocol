#!/usr/bin/env python3
"""Submit [QR CODE REGISTRATION] to Edgar.

Registers a single QR code in the Agroverse QR codes sheet and triggers
GitHub Actions for branded PNG generation.

Run:
    python -m truesight_dao_client.modules.register_qr_code --help
    # or: truesight-dao-register-qr-code --help
"""
import sys

from ..edgar_client import build_event_cli


main = build_event_cli(
    event_name='QR CODE REGISTRATION',
    canonical_labels=[
        'QR Code',
        'Landing Page',
        'Farm Name',
        'State',
        'Country',
        'Year',
        'Currency',
        'Status',
        'Manager',
    ],
    dapp_page=None,  # No DApp page yet — CLI-only
)

if __name__ == "__main__":
    sys.exit(main())
