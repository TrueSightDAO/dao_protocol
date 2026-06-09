#!/usr/bin/env bash
# Run the headless E2E test against the beta sandbox from the autopilot box.
# Usage: ./scripts/run_beta_e2e.sh [--skip-stripe]

set -euo pipefail

BETA_HOST="ubuntu@54.162.175.189"
BETA_KEY="~/.ssh/dao-protocol-beta-key"

if [ "${1:-}" = "--skip-stripe" ]; then
    echo "Running E2E test without Stripe API calls..."
    ssh -i "$BETA_KEY" "$BETA_HOST" "cd /home/ubuntu/dao_protocol && source venv/bin/activate && python -c \"
import json, urllib.request

# Test 1: ping
req = urllib.request.Request('https://beta.edgar.truesight.me/ping')
with urllib.request.urlopen(req) as r: print('Ping:', r.read().decode())

# Test 2: unsigned webhook
payload = json.dumps({'test': True}).encode()
req = urllib.request.Request('https://beta.edgar.truesight.me/stripe/subscription_webhook', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
try:
    urllib.request.urlopen(req)
    print('FAIL: expected 400')
except urllib.error.HTTPError as e:
    print(f'Unsigned webhook: {e.code} {e.read().decode()}')
\""
    exit 0
fi

# Full E2E with Stripe API
STRIPE_KEY="${STRIPE_TEST_KEY:-}"
if [ -z "$STRIPE_KEY" ]; then
    echo "ERROR: STRIPE_TEST_KEY not set"
    echo "Usage: STRIPE_TEST_KEY=sk_test_... ./scripts/run_beta_e2e.sh"
    exit 1
fi

ssh -i "$BETA_KEY" "$BETA_HOST" "STRIPE_TEST_KEY=$STRIPE_KEY" "cd /home/ubuntu/dao_protocol && source venv/bin/activate && pip install -q stripe && python tests/test_beta_sandbox_e2e.py"
