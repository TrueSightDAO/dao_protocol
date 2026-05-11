#!/usr/bin/env python3
"""Submit [BATCH QR CODE REQUEST] to Edgar.

Browser equivalent: dapp.truesight.me/batch_qr_generator.html

The DApp emits exactly two payload labels:
    - Currency: <SKU name>
    - Quantity: <integer>

Both are now CLI flags with appropriate validators (was previously
`canonical_labels=[]`, which forced every caller to use --attr and
left zero protection against typos like `--attr 'Quantity=ten'`).

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.batch_qr_generator --help

Typical use:
    python -m truesight_dao_client.modules.batch_qr_generator \\
        --currency 'Cacao Almonds (KG)' \\
        --quantity 25
"""
import sys

from ..edgar_client import build_event_cli
from ..validators import (
    currency_code,
    normalize_currency,
    positive_integer,
    required,
)

main = build_event_cli(
    event_name='BATCH QR CODE REQUEST',
    canonical_labels=['Currency', 'Quantity'],
    dapp_page='batch_qr_generator.html',
    validators={
        'Currency': currency_code,
        'Quantity': positive_integer,
    },
    normalizers={
        'Currency': normalize_currency,
    },
)

if __name__ == "__main__":
    sys.exit(main())
