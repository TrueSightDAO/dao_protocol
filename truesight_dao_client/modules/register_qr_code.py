#!/usr/bin/env python3
"""Register a single Agroverse QR code.

Two-step flow:
  1. POST signed [QR CODE REGISTRATION] event to Edgar /dao/qr_code_register
  2. GET GAS web app to trigger processing

Run:
    python -m truesight_dao_client.modules.register_qr_code --help
    # or: truesight-dao-register-qr-code --help
"""
from __future__ import annotations

import argparse
import sys

import requests

from ..edgar_client import EdgarClient

GAS_WEB_APP_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzlUS6-b3_wZaGwTVenx3pBNNNScGDt9TB0ueUyDPvbkt64zryH5QI_hrvT7i2EPYEc"
    "/exec"
)

CANONICAL_LABELS = [
    "QR Code",
    "Landing Page",
    "Farm Name",
    "State",
    "Country",
    "Year",
    "Currency",
    "Status",
    "Manager",
    "Creation Date",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register a single Agroverse QR code. "
            "Step 1: POST signed [QR CODE REGISTRATION] to Edgar. "
            "Step 2: GET GAS web app to trigger processing."
        ),
    )
    for lbl in CANONICAL_LABELS:
        flag = "--" + lbl.lower().replace(" ", "-")
        parser.add_argument(flag, default=None, metavar="VALUE", help=f'Sets "{lbl}" field.')
    parser.add_argument("--dry-run", action="store_true", help="Print payload without submitting.")
    parser.add_argument("--skip-gas", action="store_true", help="Skip the GAS trigger step.")

    args = parser.parse_args(argv)

    # Collect attributes
    attrs = {}
    for lbl in CANONICAL_LABELS:
        flag = lbl.lower().replace(" ", "-")
        val = getattr(args, flag.replace("-", "_"), None)
        if val is not None:
            attrs[lbl] = val

    if not attrs:
        parser.error("At least one attribute is required.")

    # Validate required
    required = ["QR Code", "Landing Page", "Farm Name", "Manager"]
    missing = [r for r in required if r not in attrs or not attrs[r]]
    if missing:
        parser.error(f"Missing required fields: {', '.join(missing)}")

    # Build event text
    lines = ["[QR CODE REGISTRATION]"]
    for lbl in CANONICAL_LABELS:
        if lbl in attrs:
            lines.append(f"- {lbl}: {attrs[lbl]}")
    event_text = "\n".join(lines)

    if args.dry_run:
        print("=== DRY RUN ===")
        print("Step 1: POST to Edgar")
        print(f"  URL: {EdgarClient.DEFAULT_EDGAR_BASE}/dao/qr_code_register")
        print(f"  Payload:\n{event_text}")
        print()
        print("Step 2: GET GAS web app")
        print(f"  URL: {GAS_WEB_APP_URL}")
        print(f"  Action: processQRCodeGenerationTelegramLogs")
        print()
        print("To submit for real, run without --dry-run")
        return 0

    # Step 1: POST to Edgar
    client = EdgarClient.from_env()
    print("Step 1: Submitting to Edgar...")
    try:
        payload, request_txn_id, share_text = client.sign(
            event_name="QR CODE REGISTRATION",
            attributes=attrs,
        )
        resp = client.session.post(
            f"{client.base_url}/dao/qr_code_register",
            data={"text": share_text},
            timeout=30.0,
        )
        result = resp.json()
        print(f"  Edgar response: {result.get('status', 'unknown')}")
        if result.get("status") != "success":
            print(f"  Error: {result.get('error', 'unknown')}")
            return 1
    except Exception as e:
        print(f"  Edgar submission failed: {e}")
        return 1

    # Step 2: Trigger GAS
    if not args.skip_gas:
        print("Step 2: Triggering GAS processing...")
        try:
            gas_url = f"{GAS_WEB_APP_URL}?action=processQRCodeGenerationTelegramLogs"
            gas_resp = requests.get(gas_url, timeout=60)
            print(f"  GAS response: {gas_resp.status_code}")
            body = gas_resp.text[:500]
            print(f"  Body: {body}")
        except Exception as e:
            print(f"  GAS trigger failed: {e}")
            return 1

    print()
    print(f"QR code {attrs.get('QR Code', 'unknown')} registered successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
