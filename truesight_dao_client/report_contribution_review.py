"""
report_contribution_review — CLI for submitting [CONTRIBUTION REVIEW EVENT] to Edgar.

Usage:
    truesight-dao-report-contribution-review Approve --scoring-hash-key <key> --tdgs-issued <amount> [--contributor-name <name>]
    truesight-dao-report-contribution-review Reject --scoring-hash-key <key> --rejection-reason <reason>
    truesight-dao-report-contribution-review Skip --scoring-hash-key <key>

Options:
    --keypair FILE         Path to RSA keypair JSON file (default: ~/.truesight/keypair.json)
    --beta                 Use beta.edgar.truesight.me instead of production
    --dry-run              Print the signed event without submitting
    --json                 Output result as JSON
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# ─── Constants ───────────────────────────────────────────────────────────────

PROD_EDGAR_URL = 'https://edgar.truesight.me'
BETA_EDGAR_URL = 'https://beta.edgar.truesight.me'
DEFAULT_KEYPAIR_PATH = os.path.expanduser('~/.truesight/keypair.json')


# ─── RSA Signing ─────────────────────────────────────────────────────────────

def _load_keypair(path: str) -> dict:
    """Load RSA keypair from a JSON file."""
    if not os.path.exists(path):
        print(f'Error: Keypair file not found: {path}', file=sys.stderr)
        print('Generate one with: truesight-dao-register-identity', file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def _sign_text(text: str, private_key_pem: str) -> str:
    """Sign text with an RSA private key (PKCS#8 PEM)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.backends import default_backend
    import base64

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None,
        backend=default_backend()
    )

    signature = private_key.sign(
        text.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    return base64.b64encode(signature).decode('utf-8')


def _generate_tx_id() -> str:
    """Generate a unique transaction ID."""
    now = datetime.now(timezone.utc)
    ts = now.strftime('%Y%m%d%H%M%S')
    import random
    rand = random.randint(1000, 9999)
    return f'REV-{ts}-{rand}'


# ─── Event Builder ───────────────────────────────────────────────────────────

def _build_event_text(action: str, scoring_hash_key: str, **kwargs) -> str:
    """Build the [CONTRIBUTION REVIEW EVENT] text for signing."""
    lines = [
        '[CONTRIBUTION REVIEW EVENT]',
        f'- Action: {action}',
        f'- Scoring Hash Key: {scoring_hash_key}',
    ]

    if action == 'Approve':
        tdg_issued = kwargs.get('tdgs_issued', '0.00')
        lines.append(f'- TDGs Issued: {tdg_issued}')
        contributor_name = kwargs.get('contributor_name')
        if contributor_name:
            lines.append(f'- Contributor Name: {contributor_name}')

    elif action == 'Reject':
        rejection_reason = kwargs.get('rejection_reason', '')
        lines.append(f'- Rejection Reason: {rejection_reason}')

    # Skip has no extra fields

    lines.extend([
        '',
        '--------',
        'My Digital Signature: (pending)',
        'Request Transaction ID: (pending)',
    ])

    return '\n'.join(lines)


def _build_signed_event(action: str, scoring_hash_key: str, keypair: dict, **kwargs) -> dict:
    """Build and sign the full event. Returns {text, signature, transaction_id}."""
    tx_id = _generate_tx_id()
    event_text = _build_event_text(action, scoring_hash_key, **kwargs)

    # Sign the event text (with pending placeholders)
    signature = _sign_text(event_text, keypair['privateKey'])

    # Replace placeholders
    signed_text = event_text.replace(
        'My Digital Signature: (pending)',
        f'My Digital Signature:\n{signature}'
    ).replace(
        'Request Transaction ID: (pending)',
        f'Request Transaction ID: {tx_id}'
    )

    return {
        'text': signed_text,
        'signature': signature,
        'transaction_id': tx_id,
    }


# ─── Submission ──────────────────────────────────────────────────────────────

def _submit_to_edgar(signed_text: str, edgar_url: str) -> dict:
    """Submit the signed event to Edgar's submit_contribution_review endpoint."""
    url = f'{edgar_url}/dao/submit_contribution_review'

    data = urllib.parse.urlencode({'text': signed_text}).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {'status': 'error', 'error': f'HTTP {e.code}: {body[:200]}'}
    except urllib.error.URLError as e:
        return {'status': 'error', 'error': f'Connection error: {e.reason}'}


# ─── CLI ─────────────────────────────────────────────────────────────────────

def build_event_cli() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description='Submit a [CONTRIBUTION REVIEW EVENT] to Edgar.',
        usage='''
truesight-dao-report-contribution-review <action> [options]

Actions:
  Approve    Approve a contribution with TDGs issued
  Reject     Reject a contribution with a reason
  Skip       Skip a contribution (leave for later)

Examples:
  truesight-dao-report-contribution-review Approve --scoring-hash-key XzQ2EhAMD7MN8X0zFhvw --tdgs-issued 45.00
  truesight-dao-report-contribution-review Reject --scoring-hash-key XzQ2EhAMD7MN8X0zFhvw --rejection-reason "Duplicate entry"
  truesight-dao-report-contribution-review Skip --scoring-hash-key XzQ2EhAMD7MN8X0zFhvw
''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('action', choices=['Approve', 'Reject', 'Skip'],
                        help='Action to take on the contribution')
    parser.add_argument('--scoring-hash-key', required=True,
                        help='The scoring hash key of the contribution to review')
    parser.add_argument('--tdgs-issued', type=float,
                        help='TDGs to issue (required for Approve)')
    parser.add_argument('--contributor-name',
                        help='Override contributor name (for unresolved contributors)')
    parser.add_argument('--rejection-reason',
                        help='Reason for rejection (required for Reject)')
    parser.add_argument('--keypair', default=DEFAULT_KEYPAIR_PATH,
                        help=f'Path to RSA keypair JSON (default: {DEFAULT_KEYPAIR_PATH})')
    parser.add_argument('--beta', action='store_true',
                        help='Use beta.edgar.truesight.me')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the signed event without submitting')
    parser.add_argument('--json', action='store_true',
                        help='Output result as JSON')

    return parser


def main():
    parser = build_event_cli()
    args = parser.parse_args()

    # ── Validate action-specific requirements ──
    if args.action == 'Approve' and args.tdgs_issued is None:
        parser.error('--tdgs-issued is required for Approve action')
    if args.action == 'Reject' and not args.rejection_reason:
        parser.error('--rejection-reason is required for Reject action')

    # ── Load keypair ──
    keypair = _load_keypair(args.keypair)

    # ── Build the signed event ──
    kwargs = {}
    if args.action == 'Approve':
        kwargs['tdgs_issued'] = f'{args.tdgs_issued:.2f}'
        if args.contributor_name:
            kwargs['contributor_name'] = args.contributor_name
    elif args.action == 'Reject':
        kwargs['rejection_reason'] = args.rejection_reason

    signed = _build_signed_event(args.action, args.scoring_hash_key, keypair, **kwargs)

    # ── Dry run ──
    if args.dry_run:
        if args.json:
            print(json.dumps(signed, indent=2))
        else:
            print('=== DRY RUN — Signed Event ===')
            print(signed['text'])
            print()
            print(f'Transaction ID: {signed["transaction_id"]}')
            print(f'Signature: {signed["signature"][:40]}...')
        return

    # ── Submit ──
    edgar_url = BETA_EDGAR_URL if args.beta else PROD_EDGAR_URL
    result = _submit_to_edgar(signed['text'], edgar_url)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get('status') == 'ok':
            print(f'✓ {args.action} submitted successfully.')
            print(f'  Transaction ID: {result.get("transaction_id", signed["transaction_id"])}')
        else:
            print(f'✕ Submission failed: {result.get("error", "Unknown error")}')
            sys.exit(1)


if __name__ == '__main__':
    main()
