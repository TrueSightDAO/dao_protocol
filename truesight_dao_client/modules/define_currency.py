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
#   N = Raw Request Text      (conversion/repackaging provenance)
#   O = Composition JSON      (URL to the per-batch composition file)
#   P = Inventory Type        (dropdown: States!X)
#   Q = Sale Type             (dropdown: States!Y)
#   R = GTIN
#   S = HS Code
#   T = Source Documents      (cost/provenance links)
#   U = Tree Charge
#   V = FDA Product Code      (FDA Prior Notice / border crossing)
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
    # Conversion / repackaging provenance + trade metadata (cols N-V).
    # All optional; the GAS handler writes blank cells when omitted.
    'Raw Request Text',
    'Composition JSON',
    'Inventory Type',
    'Sale Type',
    'GTIN',
    'HS Code',
    'Source Documents',
    'Tree Charge',
    'FDA Product Code',
]

VALIDATORS = {
    'Price in USD': positive_number,
    'Landing Page': url_or_empty,
    'Year': year_value,
    'Unit Weight (grams)': positive_number,
    'Unit Weight (ounces)': positive_number,
    'Composition JSON': url_or_empty,
    'Source Documents': url_or_empty,
    'Tree Charge': positive_number,
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
    'Raw Request Text': strip,
    'Composition JSON': strip,
    'Inventory Type': strip,
    'Sale Type': strip,
    'GTIN': strip,
    'HS Code': strip,
    'Source Documents': strip,
    'Tree Charge': normalize_number,
    'FDA Product Code': strip,
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
