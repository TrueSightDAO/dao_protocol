#!/usr/bin/env python3
"""Submit [CURRENCY DEFINITION EVENT] to Edgar.

Defines a QR-ready serializable currency in the Currencies tab end-to-end
via Edgar - no gspread required. Handles the SKU-backed case too: pass
``--sku-product-id`` and the GAS handler infers "Serializable" from real
SKU stock (col I of "Agroverse SKUs").

Browser equivalent: dapp.truesight.me/define_currency.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.define_currency --help

Typical use (SKU-backed, price/unit cost captured, auto-serialize):
    python -m truesight_dao_client.modules.define_currency \
        --currency 'Ceremonial Cacao (250g)' \
        --sku-product-id 'oscar-bahia-ceremonial-cacao-200g' \
        --price 25.00 \
        --unit 'oz' \
        --weight 7.05 \
        --landing-page 'https://truesight.me/shop/ceremonial-cacao' \
        --ledger 'AGROVERSE' \
        --farm-name 'Oscar Farm' \
        --state 'Bahia' \
        --country 'Brazil' \
        --year 2026 \
        --dry-run
"""
from __future__ import annotations

import sys

from ..edgar_client import build_event_cli
from ..validators import (
    normalize_currency,
    normalize_number,
    positive_number,
    strip,
    url_or_empty,
    year_value,
)

# Canonical label list - maps to Currencies tab columns A-M:
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
#   M = SKU Product ID
#
# "Serializable" (C) defaults to TRUE. When `SKU Product ID` (M) is supplied
# and no explicit `--serializable` override is given, the GAS handler infers
# TRUE/FALSE from the SKU's real stock instead of trusting the default - so
# an in-stock SKU serializes without a manual flag, and a zero-stock SKU is
# not silently mis-marked TRUE.
#
# Only `Currency` is mandatory; every other label may be left empty (empty
# `Serializable` becomes the TRUE default; empty `Year` is allowed).
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
    'SKU Product ID',
]

VALIDATORS = {
    'Price in USD': positive_number,
    'Landing Page': url_or_empty,
    'Year': year_value,
    'Unit Weight (grams)': positive_number,
    'Unit Weight (ounces)': positive_number,
}

NORMALIZERS = {
    'Currency': normalize_currency,
    'Price in USD': normalize_number,
    'Unit Weight (grams)': normalize_number,
    'Unit Weight (ounces)': normalize_number,
    'Farm Name': strip,
    'State': strip,
    'Country': strip,
    'Ledger': strip,
    'Landing Page': strip,
    'SKU Product ID': strip,
}

DEFAULTS = {
    'Serializable': 'TRUE',
}

REQUIRED_LABELS = ['Currency']


def main(argv: list[str] | None = None) -> int:
    inner = build_event_cli(
        event_name='CURRENCY DEFINITION EVENT',
        canonical_labels=LABELS,
        dapp_page='define_currency.html',
        validators=VALIDATORS,
        normalizers=NORMALIZERS,
        defaults=DEFAULTS,
        required_labels=REQUIRED_LABELS,
    )
    return inner(argv)


if __name__ == "__main__":
    sys.exit(main())
