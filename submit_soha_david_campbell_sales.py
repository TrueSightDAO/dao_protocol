#!/usr/bin/env python3
"""
Submit 40 [SALES EVENT] for SOHA - David Campbell's bulk cacao purchase.
One event per QR code. Cash sale — no Stripe.
Receipt: ~/Applications/tmp/SOHA_sales.PNG
"""
import sys
import time

sys.path.insert(0, "/Users/garyjob/Applications/dao_client")

from truesight_dao_client.edgar_client import EdgarClient

# === Transaction details ===
OWNER_EMAIL = "david@soha.center"
SOLD_BY = "SOHA - David Campbell"
CASH_COLLECTED_BY = "Gary Teh"
SALES_PRICE = "17.00"
GENERATION_SOURCE = "dao_client / bulk cash sale, local pickup"

# === 40 QR codes across 3 batches ===
QR_CODES = [
    # Batch 1 — 2024OSCAR_20260330 (24 bags)
    "2024OSCAR_20260330_1",
    "2024OSCAR_20260330_2",
    "2024OSCAR_20260330_3",
    "2024OSCAR_20260330_4",
    "2024OSCAR_20260330_5",
    "2024OSCAR_20260330_6",
    "2024OSCAR_20260330_7",
    "2024OSCAR_20260330_8",
    "2024OSCAR_20260330_9",
    "2024OSCAR_20260330_10",
    "2024OSCAR_20260330_11",
    "2024OSCAR_20260330_12",
    "2024OSCAR_20260330_13",
    "2024OSCAR_20260330_14",
    "2024OSCAR_20260330_15",
    "2024OSCAR_20260330_17",
    "2024OSCAR_20260330_19",
    "2024OSCAR_20260330_20",
    "2024OSCAR_20260330_21",
    "2024OSCAR_20260330_22",
    "2024OSCAR_20260330_30",
    "2024OSCAR_20260330_34",
    "2024OSCAR_20260330_35",
    "2024OSCAR_20260330_36",
    # Batch 2 — 2024OSCAR_20260121 (9 bags)
    "2024OSCAR_20260121_22",
    "2024OSCAR_20260121_24",
    "2024OSCAR_20260121_25",
    "2024OSCAR_20260121_26",
    "2024OSCAR_20260121_27",
    "2024OSCAR_20260121_28",
    "2024OSCAR_20260121_29",
    "2024OSCAR_20260121_30",
    "2024OSCAR_20260121_31",
    # Batch 3 — 2024SA_20251227 (7 bags)
    "2024SA_20251227_35",
    "2024SA_20251227_36",
    "2024SA_20251227_37",
    "2024SA_20251227_38",
    "2024SA_20251227_39",
    "2024SA_20251227_40",
    "2024SA_20251227_42",
]

TOTAL_BAGS = len(QR_CODES)
assert TOTAL_BAGS == 40, f"Expected 40 QR codes, got {TOTAL_BAGS}"


def build_attrs(qr_code: str, index: int) -> list[tuple[str, str]]:
    return [
        ("Item", qr_code),
        ("Sales price", SALES_PRICE),
        ("Sold by", SOLD_BY),
        ("Cash proceeds collected by", CASH_COLLECTED_BY),
        ("Owner email", OWNER_EMAIL),
        ("Submission Source", GENERATION_SOURCE),
        ("Bulk order index", f"{index + 1} of {TOTAL_BAGS}"),
    ]


def main(dry_run: bool = False) -> int:
    client = EdgarClient.from_env(path="/Users/garyjob/Applications/dao_client/.env")
    client.generation_source = GENERATION_SOURCE

    print(f"Submitting {TOTAL_BAGS} [SALES EVENT] to Edgar")
    print(f"  Sold by: {SOLD_BY}")
    print(f"  Price per bag: ${SALES_PRICE}")
    print(f"  Total: ${float(SALES_PRICE) * TOTAL_BAGS:.2f}")
    print(f"  Cash collected by: {CASH_COLLECTED_BY}")
    print(f"  Owner email: {OWNER_EMAIL}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print()

    success_count = 0
    fail_count = 0

    for idx, qr in enumerate(QR_CODES):
        attrs = build_attrs(qr, idx)
        print(f"[{idx + 1:2d}/{TOTAL_BAGS}] {qr} … ", end="", flush=True)

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

        if idx < len(QR_CODES) - 1:
            time.sleep(1.0)

    print(f"\nDone. Success: {success_count}, Failed: {fail_count}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
