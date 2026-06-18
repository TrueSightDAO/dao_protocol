#!/usr/bin/env python3
"""
Template: Bulk serialized QR code sales via dao_client -> Edgar.

Use this when a customer buys multiple serialized chocolate bars (each has its own
QR code) in a single transaction. One [SALES EVENT] is required per QR code.

Prerequisites:
  - dao_client venv activated (or installed with `pip install -e .`)
  - `.env` with EMAIL, PUBLIC_KEY, PRIVATE_KEY
  - Stripe Session ID / PaymentIntent ID from the confirmed payment
  - Exact Currency string from `agroverse-inventory/currencies.json`

Workflow:
  1. Discover QR codes via GAS endpoint (?list_with_members=true)
  2. One [SALES EVENT] per QR code (Item = QR code ID) — SUFFICIENT on its own;
     downstream (QR Code Sales tab -> offchain transactions -> treasury cache)
     depletes inventory AUTOMATICALLY. Do NOT add an [INVENTORY MOVEMENT] to
     "deplete": that event only transfers inventory custody person-to-person,
     it is not a depletion step and is not part of the sales flow.
  3. Optional: [QR CODE UPDATE EVENT] if GAS does not auto-flip status

See also:
  - agentic_ai_context/notes/claude_serialized_qr_sales_2026-04-29.md (full playbook)
  - dao_client/modules/report_sales.py (SALES EVENT CLI)
  - dao_client/modules/report_inventory_movement.py (INVENTORY MOVEMENT CLI)
"""

import json
import time
import urllib.request
from truesight_dao_client.edgar_client import EdgarClient

# ---------------------------------------------------------------------------
# CONFIG — customize these values for each sale
# ---------------------------------------------------------------------------

# GAS endpoint for QR discovery (anonymous, no auth required)
GAS_QR_ENDPOINT = (
    "https://script.google.com/macros/s/"
    "AKfycbxigq4-J0izShubqIC5k6Z7fgNRyVJLakfQ34HPuENiSpxuCG-wSq0g-wOAedZzzgaL/exec"
)

# Sale metadata
SOLD_BY = "Kirsten Ritschel"
CASH_COLLECTED_BY = "Kirsten Ritschel"
OWNER_EMAIL = "kiki@kikiscocoa.com"      # adjust per transaction

# Payment type:
#   - Stripe checkout:  STRIPE_SESSION_ID = "cs_live_..." (from Stripe dashboard)
#   - Cash sale:        STRIPE_SESSION_ID = "(none)"
#                       Do NOT use "N/A" — GAS treats it as a literal string.
STRIPE_SESSION_ID = "cs_live_..."

SHIPPING_PROVIDER = "N/A"                 # "N/A" for local pickup / hand delivery
TRACKING_NUMBER = "N/A"                   # "N/A" for local pickup
ATTACHED_FILENAME = "receipt.pdf"         # or "N/A" if no receipt file
SUBMISSION_SOURCE = "dao_client/bulk_qr_sales_template.py"

# Pricing (set exactly one of these)
PER_BAR_GROSS = 10.00                     # e.g. $10.00 per bar
TOTAL_STRIPE_FEE = 11.03                  # total Stripe fee for the whole txn
# PER_BAR_FEE will be computed: TOTAL_STRIPE_FEE / number_of_bars

# Ledger vs physical possession note:
#   The QR code's ledger_shortcut (e.g. agl4, agl6) tracks which ledger owns the
#   record. The item can physically be anywhere (e.g. in your car). The manager_name
#   tracks who manages the record, not who holds the bag.

# QR discovery filters
CONTRIBUTOR_NAME = "Kirsten Ritschel"
CURRENCY = "81% Dark Chocolate Bar 50grams - Oscar Fazenda, Brazil 2024 + CP340993988BR San Francisco"
STATUS = "MINTED"

# ---------------------------------------------------------------------------
# STEP 1: Discover QR codes
# ---------------------------------------------------------------------------


def discover_qr_codes():
    url = f"{GAS_QR_ENDPOINT}?list_with_members=true"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    codes = []
    for row in data.get("data", []):
        if (
            row.get("contributor_name") == CONTRIBUTOR_NAME
            and row.get("currency") == CURRENCY
            and row.get("status") == STATUS
        ):
            codes.append(row["qr_code"])

    codes.sort()
    print(f"Discovered {len(codes)} QR codes for {CURRENCY}")
    for c in codes:
        print(f"  - {c}")
    return codes


# ---------------------------------------------------------------------------
# STEP 2: Submit [SALES EVENT] per QR code
# ---------------------------------------------------------------------------


def submit_sales_events(qr_codes):
    client = EdgarClient.from_env()
    per_bar_fee = round(TOTAL_STRIPE_FEE / len(qr_codes), 4)

    for i, qr in enumerate(qr_codes, start=1):
        attrs = {
            "Item": qr,
            "Sales price": str(PER_BAR_GROSS),
            "Sold by": SOLD_BY,
            "Cash proceeds collected by": CASH_COLLECTED_BY,
            "Owner email": OWNER_EMAIL,
            "Stripe Session ID": STRIPE_SESSION_ID,
            "Shipping Provider": SHIPPING_PROVIDER,
            "Tracking number": TRACKING_NUMBER,
            "Attached Filename": ATTACHED_FILENAME,
            "Submission Source": SUBMISSION_SOURCE,
            # Fee amortization (optional but recommended for bookkeeping)
            "Stripe Fee Per Bar": str(per_bar_fee),
            "Gross Per Bar": str(PER_BAR_GROSS),
            "Net Per Bar": str(round(PER_BAR_GROSS - per_bar_fee, 4)),
        }

        print(f"[{i}/{len(qr_codes)}] Submitting SALES EVENT for {qr} ...")
        resp = client.submit("SALES EVENT", attrs)
        print(f"       -> {resp.status_code} {resp.reason}")
        time.sleep(1)  # be polite to Edgar / GAS

    print("All SALES EVENT submissions complete.")


# ---------------------------------------------------------------------------
# OPTIONAL custody transfer — [INVENTORY MOVEMENT]
# NOT a sales/depletion step. A sale needs ONLY the [SALES EVENT] above
# (downstream auto-depletes). Use this ONLY when you actually need to reassign
# physical custody of the items from one person to another.
# ---------------------------------------------------------------------------


def submit_inventory_movement(qr_codes, inventory_item, destination):
    """
    Transfer inventory custody from one person to another (NOT a depletion).

    A sale does not require this — the [SALES EVENT] alone is sufficient and
    inventory depletion happens automatically downstream. Use this only to
    reassign who physically holds the items.

    Parameters:
      qr_codes     : list of QR code IDs sold
      inventory_item: exact Currency string (same as used for discovery)
      destination  : e.g. "Sold to Customer" or the buyer's name
    """
    client = EdgarClient.from_env()

    for i, qr in enumerate(qr_codes, start=1):
        attrs = {
            "Manager Name": SOLD_BY,
            "Recipient Name": destination,
            "Inventory Item": inventory_item,
            "QR Code": qr,
            "Quantity": "1",
            "Latitude": "N/A",
            "Longitude": "N/A",
            "Attached Filename": "N/A",
            "Destination Inventory File Location": "N/A",
            "Submission Source": SUBMISSION_SOURCE,
        }

        print(f"[{i}/{len(qr_codes)}] Submitting INVENTORY MOVEMENT for {qr} ...")
        resp = client.submit("INVENTORY MOVEMENT", attrs)
        print(f"       -> {resp.status_code} {resp.reason}")
        time.sleep(1)

    print("All INVENTORY MOVEMENT submissions complete.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    qr_codes = discover_qr_codes()
    if not qr_codes:
        print("No QR codes found. Aborting.")
        exit(1)

    # Uncomment after verifying discovery output:
    # submit_sales_events(qr_codes)

    # Uncomment after sales events are confirmed:
    # submit_inventory_movement(
    #     qr_codes,
    #     inventory_item=CURRENCY,
    #     destination="Elizabeth Wong"   # or "Sold to Customer"
    # )
