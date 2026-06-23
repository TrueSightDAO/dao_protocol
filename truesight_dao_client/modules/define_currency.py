#!/usr/bin/env python3
"""Submit [CURRENCY DEFINITION EVENT] to Edgar.

Defines a QR-ready serializable currency in the Currencies tab end-to-end
via Edgar — no gspread required. The GAS handler (PR2) appends a row to
cols A–L and sorts A→Z, so the new SKU is immediately QR-ready for
`truesight-dao-batch-qr-generator`.

Browser equivalent: (no DApp page — CLI-only primitive)

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.define_currency --help

Typical use:
    python -m truesight_dao_client.modules.define_currency \
        --currency 'Ceremonial Cacao (250g)' \
        --price 25.00 \
        --serializable TRUE \
        --landing-page 'https://truesight.me/shop/ceremonial-cacao' \
        --ledger 'AGROVERSE' \
        --farm-name 'Fazenda Rendimento' \
        --state 'Bahia' \
        --country 'Brazil' \
        --year 2026 \
        --unit-weight-grams 250 \
        --dry-run
"""
from __future__ import annotations

import sys

from ..edgar_client import build_event_cli
from ..validators import (
    currency_code,
    normalize_currency,
    positive_number,
    required,
    url_or_empty,
    yyyymmdd_date,
)

# Canonical label list — maps to Currencies tab columns A–L:
#   A = Currency (name)
#   B = Price in USD
#   C = Serializable
#   D = Product Image
#   E = Landing Page
#   F = Ledger
#   G = Farm Name
#   H = State
#   I = Country
#   J = Year
#   K = Unit Weight (grams)
#   L = Unit Weight (ounces)
#
# Required for QR-ready: A, C=TRUE, E, F, G, H, I, J.
# B/D/K/L are recommended but optional.
LABELS = [
    'Currency',
    'Price in USD',
    'Serializable',
    'Product Image',
    'Landing Page',
    'Ledger',
    'Farm Name',
    'State',
    'Country',
    'Year',
    'Unit Weight (grams)',
    'Unit Weight (ounces)',
]

VALIDATORS = {
    'Currency': currency_code,
    'Price in USD': positive_number,
    'Landing Page': url_or_empty,
    'Farm Name': required,
    'State': required,
    'Country': required,
    'Year': yyyymmdd_date,
}

NORMALIZERS = {
    'Currency': normalize_currency,
}

DEFAULTS = {
    'Serializable': 'TRUE',
}


def main(argv: list[str] | None = None) -> int:
    inner = build_event_cli(
        event_name='CURRENCY DEFINITION EVENT',
        canonical_labels=LABELS,
        dapp_page=None,
        validators=VALIDATORS,
        normalizers=NORMALIZERS,
        defaults=DEFAULTS,
    )
    return inner(argv)


if __name__ == "__main__":
    sys.exit(main())
