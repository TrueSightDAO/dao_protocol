#!/usr/bin/env python3
"""Submit `[DONATION MINT EVENT]` to Edgar for a serialized SunMint Pledge QR code.

Mints one row on `Agroverse QR codes` (status=MINTED) representing a cash donation
toward SunMint Tree Planting. The operator's subsequent `report_sales` call flips
the status to SOLD via the existing sales pipeline.

Three gates enforced server-side by the GAS handler before minting (this CLI is a
thin signer that only assembles the payload — server-side gates are authoritative):

  1. Currency must be `SunMint Tree Planting Pledge - QR Code` (V1 allowlist).
  2. Signer must be a DAO governor (Pattern A — GAS reads the `Governors` tab).
  3. Visual proof URL must point to `github.com/TrueSightDAO/...`.

The QR code identifier is **client-generated** so the operator can immediately fire
`report_sales --item <qr_id>` without polling.

Visual proof flows through Edgar:
  - The dao_client sends the local proof file's **bytes** via multipart upload
    (`attachment` field).
  - The CLI computes a destination URL of the form
    `https://github.com/TrueSightDAO/.github/blob/main/assets/donations/<basename>`
    and includes it as `Destination Contribution File Location:` in the signed
    event payload.
  - Edgar parses that URL, reads the multipart bytes, and uploads to GitHub via
    the Contents API using `config.github_pat`. The dao_client never holds a
    GitHub token.

Usage:

    cd ~/Applications/dao_client
    source .venv/bin/activate

    python -m truesight_dao_client.modules.mint_donation \\
        --donation-amount 25 \\
        --donor-name "Will" \\
        --donor-email will@example.com \\
        --proof-file ~/Downloads/wills_donation_venmo_screenshot.PNG

    # The CLI prints the freshly-minted QR code id (e.g. PLEDGE_20260430_a1b2c3d4)
    # AND the destination URL Edgar uploaded the proof to. Use the QR id in the next
    # step:

    python -m truesight_dao_client.modules.report_sales \\
        --item PLEDGE_20260430_a1b2c3d4 \\
        --sales-price 25 \\
        --sold-by "Gary Teh" --cash-proceeds-collected-by "Gary Teh" \\
        --owner-email will@example.com \\
        --stripe-session-id "(none)" \\
        --shipping-provider N/A --tracking-number N/A
"""
from __future__ import annotations

import argparse
import datetime as _dt
import secrets
import sys
from pathlib import Path

from ..edgar_client import EdgarClient

EVENT_NAME = "DONATION MINT EVENT"
DEFAULT_CURRENCY = "SunMint Tree Planting Pledge - QR Code"
DEFAULT_QR_PREFIX = "PLEDGE"
# All proof files land under TrueSightDAO/.github/assets/donations/. Edgar's PAT
# covers this repo per `sentiment_importer/config/application.rb` config.github_pat.
PROOF_GITHUB_OWNER = "TrueSightDAO"
PROOF_GITHUB_REPO = ".github"
PROOF_GITHUB_BRANCH = "main"
PROOF_GITHUB_DIR = "assets/donations"


def _today_yyyymmdd() -> str:
    return _dt.datetime.utcnow().strftime("%Y%m%d")


def generate_qr_code(prefix: str = DEFAULT_QR_PREFIX) -> str:
    """Stable, client-generated QR id: ``<PREFIX>_<YYYYMMDD>_<8hex>``."""
    return f"{prefix}_{_today_yyyymmdd()}_{secrets.token_hex(4)}"


def proof_destination_url(filename: str) -> str:
    """Compute the GitHub URL Edgar will upload the proof file to."""
    return (
        f"https://github.com/{PROOF_GITHUB_OWNER}/{PROOF_GITHUB_REPO}/"
        f"blob/{PROOF_GITHUB_BRANCH}/{PROOF_GITHUB_DIR}/{filename}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submit [DONATION MINT EVENT] to Edgar for a serialized SunMint Pledge QR. "
            "Edgar handles the GitHub upload of the proof file via multipart attachment — "
            "the dao_client never holds a GitHub token. Server-side: 3-gate validation "
            "(currency / governor / visual proof) before minting on Agroverse QR codes."
        ),
    )
    parser.add_argument("--donation-amount", required=True, help="USD amount of the donation (numeric).")
    parser.add_argument("--donor-name", required=True, help="Display name of the donor.")
    parser.add_argument("--donor-email", default="", help="Donor's email — written to Owner Email on Agroverse QR codes. Optional: programs that key holders by credential identity (e.g. Butterfly Effect pk_hash) have no email; leave empty.")
    parser.add_argument("--landing-page", default=None, help="Per-row consumer scan target (col B). Optional override of the Currency's default landing_page — e.g. a program member's credential profile_url so scanning the tree resolves to their certificate page.")
    parser.add_argument(
        "--proof-file",
        required=True,
        help=(
            f"Path to the local proof file (e.g. Venmo screenshot). The dao_client sends the "
            f"bytes via multipart attachment; Edgar uploads to "
            f"github.com/{PROOF_GITHUB_OWNER}/{PROOF_GITHUB_REPO}/blob/{PROOF_GITHUB_BRANCH}/"
            f"{PROOF_GITHUB_DIR}/<basename>."
        ),
    )
    parser.add_argument(
        "--currency",
        default=DEFAULT_CURRENCY,
        help=f'Override the donation-eligible currency (default: "{DEFAULT_CURRENCY}"). '
             "GAS server-side allowlist will reject unknown values.",
    )
    parser.add_argument(
        "--qr-code",
        default=None,
        help="Override the auto-generated QR code id (advanced; rarely needed).",
    )
    parser.add_argument(
        "--qr-code-prefix",
        default=DEFAULT_QR_PREFIX,
        help=f"Prefix for the auto-generated QR id (default: {DEFAULT_QR_PREFIX}).",
    )
    parser.add_argument(
        "--proof-filename-prefix",
        default=None,
        help=(
            "Optional filename prefix for the GitHub destination (default: derived from QR id). "
            "Final destination: <prefix>_<basename>. Useful when multiple mints share one source "
            "image — gives each its own GitHub object so subsequent mints don't 409 against the "
            "same path."
        ),
    )
    parser.add_argument("--notes", default="", help='Free-form notes appended to the event payload.')
    parser.add_argument(
        "--generation-source",
        default=None,
        help='Override the "This submission was generated using ..." footer.',
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the signed share text only; do not submit.")
    args = parser.parse_args(argv)

    # Local pre-flight
    try:
        amount = float(args.donation_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        parser.error(f"--donation-amount must be a positive number, got {args.donation_amount!r}")

    proof_path = Path(args.proof_file).expanduser().resolve()
    if not proof_path.is_file():
        parser.error(f"--proof-file not found: {proof_path}")

    qr_code = (args.qr_code or generate_qr_code(args.qr_code_prefix)).strip()

    # Per-mint unique destination filename: <qr_id_or_custom_prefix>_<original_basename>.
    # Without per-mint uniqueness, multiple mints sharing one source image would all
    # try to upload to the same GitHub path — Edgar's existing controller 409s if the
    # path already exists with different content; same content is treated as success.
    # Adding the QR id as prefix sidesteps the question entirely.
    name_prefix = args.proof_filename_prefix or qr_code
    dest_filename = f"{name_prefix}_{proof_path.name}"
    dest_url = proof_destination_url(dest_filename)

    cash_collected_iso = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Server-locked fields (landing_page, ledger, Ledger Name) intentionally absent
    # from the payload — GAS derives them from the Currencies tab. See
    # process_donation_mint_telegram_logs.gs.
    attrs: list[tuple[str, str]] = [
        ("QR Code", qr_code),
        ("Currency", args.currency),
        ("Donation Amount", f"{amount:g}"),
        ("Donor Name", args.donor_name),
        ("Donor Email", args.donor_email),
        ("Cash collected at (UTC)", cash_collected_iso),
        *( [("Landing Page", args.landing_page)] if args.landing_page else [] ),
        ("Attached Filename", dest_filename),
        ("Destination Contribution File Location", dest_url),
    ]
    if args.notes.strip():
        attrs.append(("Notes", args.notes.strip()))

    client = EdgarClient.from_env()
    if args.generation_source:
        client.generation_source = args.generation_source

    if args.dry_run:
        _, _, share_text = client.sign(EVENT_NAME, attrs)
        print(share_text)
        print(f"\nGenerated QR Code: {qr_code}")
        print(f"Proof destination: {dest_url}")
        print(f"Proof local file:  {proof_path}")
        return 0

    resp = client.submit(EVENT_NAME, attrs, attached_file_path=str(proof_path))
    print(f"HTTP {resp.status_code}")
    try:
        import json
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print(resp.text)

    if resp.ok:
        print(f"\nMinted QR Code: {qr_code}")
        print(f"Proof uploaded to: {dest_url}")
        print(
            "\nNext step — fire the SALES EVENT to flip MINTED → SOLD and land funds on the AGL ledger:\n"
            f"  python -m truesight_dao_client.modules.report_sales \\\n"
            f"    --item {qr_code} \\\n"
            f"    --sales-price {amount:g} \\\n"
            f'    --sold-by "<your-name>" --cash-proceeds-collected-by "<your-name>" \\\n'
            f"    --owner-email {args.donor_email} \\\n"
            f'    --stripe-session-id "(none)" --shipping-provider N/A --tracking-number N/A'
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
