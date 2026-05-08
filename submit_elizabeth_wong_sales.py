#!/usr/bin/env python3
"""
Submit 37 [SALES EVENT] for Elizabeth Wong's bulk chocolate bar purchase.
One event per QR code. Stripe fee amortized evenly across all 37 bars.
"""
import sys
import time

sys.path.insert(0, "/Users/garyjob/Applications/dao_client")

from truesight_dao_client.edgar_client import EdgarClient

# === Transaction details ===
CUSTOMER_EMAIL = "ewong@gogreatop.com"
STRIPE_SESSION_ID = "cs_live_a1LG0YSUtpA4U7sN9E0KbgY00LwOI7IT3N3qKQrrSNiBy3O1LPIGauKei9"
SOLD_BY = "Kirsten Ritschel"
CASH_COLLECTED_BY = "Gary Teh"
ATTACHED_FILENAME = "New Order_ Elizabeth Wong - $370.00.pdf"
GENERATION_SOURCE = "dao_client / bulk Stripe checkout, local pickup"

# === Fee amortization ===
TOTAL_STRIPE_FEE = 11.03
TOTAL_BARS = 37
GROSS_PER_BAR = 10.00
FEE_PER_BAR = round(TOTAL_STRIPE_FEE / TOTAL_BARS, 4)
NET_PER_BAR = round(GROSS_PER_BAR - FEE_PER_BAR, 4)

# === QR codes from live GAS endpoint (verified 2026-04-29) ===
OSCAR_QR_CODES = [
    "2024OSR_81PB_20260412_3", "2024OSR_81PB_20260412_4", "2024OSR_81PB_20260412_5",
    "2024OSR_81PB_20260412_6", "2024OSR_81PB_20260412_7", "2024OSR_81PB_20260412_8",
    "2024OSR_81PB_20260412_9", "2024OSR_81PB_20260412_10", "2024OSR_81PB_20260412_12",
    "2024OSR_81PB_20260412_13", "2024OSR_81PB_20260412_14", "2024OSR_81PB_20260412_15",
    "2024OSR_81PB_20260412_16", "2024OSR_81PB_20260412_17", "2024OSR_81PB_20260412_18",
    "2024OSR_81PB_20260412_19", "2024OSR_81PB_20260412_20", "2024OSR_81PB_20260412_21",
    "2024OSR_81PB_20260412_22", "2024OSR_81PB_20260412_23",
]

SANTA_ANA_QR_CODES = [
    "2023SA_81PB_20260412_1", "2023SA_81PB_20260412_5", "2023SA_81PB_20260412_6",
    "2023SA_81PB_20260412_7", "2023SA_81PB_20260412_8", "2023SA_81PB_20260412_9",
    "2023SA_81PB_20260412_10", "2023SA_81PB_20260412_11", "2023SA_81PB_20260412_12",
    "2023SA_81PB_20260412_13", "2023SA_81PB_20260412_14", "2023SA_81PB_20260412_15",
    "2023SA_81PB_20260412_16", "2023SA_81PB_20260412_17", "2023SA_81PB_20260412_18",
    "2023SA_81PB_20260412_19", "2023SA_81PB_20260412_20",
]

ALL_QR_CODES = OSCAR_QR_CODES + SANTA_ANA_QR_CODES
assert len(ALL_QR_CODES) == TOTAL_BARS, f"Expected {TOTAL_BARS} QR codes, got {len(ALL_QR_CODES)}"


def build_attrs(qr_code: str, index: int) -> list[tuple[str, str]]:
    """Return ordered attributes for one [SALES EVENT]."""
    return [
        ("Item", qr_code),
        ("Sales price", f"{GROSS_PER_BAR:.2f}"),
        ("Sold by", SOLD_BY),
        ("Cash proceeds collected by", CASH_COLLECTED_BY),
        ("Owner email", CUSTOMER_EMAIL),
        ("Stripe Session ID", STRIPE_SESSION_ID),
        ("Shipping Provider", "N/A"),
        ("Tracking number", "N/A"),
        ("Attached Filename", ATTACHED_FILENAME),
        ("Submission Source", GENERATION_SOURCE),
        # Fee amortization metadata
        ("Stripe fee per bar", f"{FEE_PER_BAR:.4f}"),
        ("Stripe fee total", f"{TOTAL_STRIPE_FEE:.2f}"),
        ("Net after fees per bar", f"{NET_PER_BAR:.4f}"),
        ("Bulk order index", f"{index + 1} of {TOTAL_BARS}"),
    ]


def main(dry_run: bool = False) -> int:
    client = EdgarClient.from_env(path="/Users/garyjob/Applications/dao_client/.env")
    client.generation_source = GENERATION_SOURCE

    print(f"Submitting {TOTAL_BARS} [SALES EVENT] to Edgar")
    print(f"  Gross per bar: ${GROSS_PER_BAR:.2f}")
    print(f"  Stripe fee per bar: ${FEE_PER_BAR:.4f} (total ${TOTAL_STRIPE_FEE:.2f})")
    print(f"  Net per bar: ${NET_PER_BAR:.4f}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print()

    success_count = 0
    fail_count = 0

    for idx, qr in enumerate(ALL_QR_CODES):
        attrs = build_attrs(qr, idx)
        print(f"[{idx + 1:2d}/{TOTAL_BARS}] {qr} … ", end="", flush=True)

        if dry_run:
            payload, txn_id, share_text = client.sign("SALES EVENT", attrs)
            print("DRY-RUN OK")
            if idx == 0:
                print("\n--- First event payload preview ---")
                print(share_text[:600] + "\n...\n")
            continue

        try:
            resp = client.submit("SALES EVENT", attrs)
            if resp.ok:
                print(f"HTTP {resp.status_code} OK")
                success_count += 1
            else:
                print(f"HTTP {resp.status_code} FAIL: {resp.text[:120]}")
                fail_count += 1
        except Exception as e:
            print(f"EXCEPTION: {e}")
            fail_count += 1

        # Be polite to Edgar — 1 s delay between calls
        if idx < len(ALL_QR_CODES) - 1:
            time.sleep(1.0)

    print(f"\nDone. Success: {success_count}, Failed: {fail_count}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
