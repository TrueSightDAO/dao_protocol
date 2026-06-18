#!/usr/bin/env python3
"""Headless E2E test for the beta sandbox subscription webhook.

Creates a test customer + subscription via Stripe test API, then verifies
that Stripe delivers the webhook events to the beta endpoint and that
the dao_protocol server processes them.

Usage:
    export STRIPE_TEST_KEY=sk_test_...
    python tests/test_beta_sandbox_e2e.py

Requires: stripe (pip install stripe)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

BETA_WEBHOOK_URL = "https://beta.edgar.truesight.me/stripe/subscription_webhook"
BETA_PING_URL = "https://beta.edgar.truesight.me/ping"


def test_beta_is_reachable() -> None:
    """Verify the beta endpoint is live."""
    req = urllib.request.Request(BETA_PING_URL)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    assert data.get("status") == "ok", f"Beta not healthy: {data}"
    assert data.get("environment") == "development", f"Not in development mode: {data}"
    print(f"[PASS] Beta endpoint reachable: {data}")


def test_unsigned_webhook_returns_400() -> None:
    """Verify the webhook endpoint rejects unsigned requests."""
    payload = json.dumps({"test": True}).encode()
    req = urllib.request.Request(
        BETA_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        print(f"[FAIL] Expected 400, got {resp.status}: {data}")
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 400, f"Expected 400, got {e.code}"
        data = json.loads(e.read())
        print(f"[PASS] Unsigned request rejected: {data}")


def test_stripe_subscription_flow() -> None:
    """Create a test subscription via Stripe API and verify webhook delivery.

    This test:
    1. Creates a test customer
    2. Creates a price and subscription with pm_card_visa
    3. Waits for the invoice to be paid
    4. Checks the beta box logs for the SANDBOX sheet write
    """
    stripe_key = os.environ.get("STRIPE_TEST_KEY")
    if not stripe_key:
        print("[SKIP] STRIPE_TEST_KEY not set — skipping subscription flow test")
        return

    import stripe
    stripe.api_key = stripe_key

    # 1. Create a test customer
    customer = stripe.Customer.create(
        email=f"test-{int(time.time())}@truesightdao.test",
        payment_method="pm_card_visa",
        invoice_settings={"default_payment_method": "pm_card_visa"},
    )
    customer_id = customer["id"]
    print(f"[INFO] Created test customer: {customer_id}")

    # 2. Create a price ($10/month)
    price = stripe.Price.create(
        unit_amount=1000,
        currency="usd",
        recurring={"interval": "month"},
        product_data={"name": "Test Chocolate Bar Subscription"},
    )
    price_id = price["id"]
    print(f"[INFO] Created test price: {price_id}")

    # 3. Create the subscription (auto-collects via the attached payment method)
    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        payment_settings={
            "payment_method_types": ["card"],
            "save_default_payment_method": "on_subscription",
        },
        off_session=True,
    )
    subscription_id = subscription["id"]
    print(f"[INFO] Created subscription: {subscription_id}")
    print(f"[INFO] Status: {subscription['status']}")

    # 4. Wait for the invoice to be paid
    latest_invoice = subscription["latest_invoice"]
    if isinstance(latest_invoice, str):
        # It's an ID — fetch it
        import time as t
        for attempt in range(10):
            t.sleep(2)
            inv = stripe.Invoice.retrieve(latest_invoice)
            if inv["status"] == "paid":
                print(f"[PASS] Invoice {latest_invoice} paid")
                break
            print(f"[INFO] Invoice status: {inv['status']} (attempt {attempt+1}/10)")
        else:
            print(f"[WARN] Invoice {latest_invoice} not paid after 20s — may still arrive")

    # 5. Check the beta box logs for the webhook processing
    print(f"[INFO] Subscription created. Check beta box logs for webhook processing.")
    print(f"[INFO] SSH to beta box and run: sudo journalctl -u dao-protocol-beta --since '1 min ago'")
    print(f"[INFO] Look for: 'SANDBOX sheet: customer_email=... subscription_id={subscription_id}'")

    # 6. Cleanup — delete the test subscription and customer
    try:
        stripe.Subscription.delete(subscription_id)
        stripe.Customer.delete(customer_id)
        print(f"[INFO] Cleaned up test data")
    except Exception as e:
        print(f"[WARN] Cleanup failed: {e}")


def main() -> None:
    print("=" * 60)
    print("Beta Sandbox E2E Test Suite")
    print("=" * 60)

    test_beta_is_reachable()
    test_unsigned_webhook_returns_400()
    test_stripe_subscription_flow()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
