#!/usr/bin/env python3
"""Headless E2E test for Stripe subscription webhook against the beta sandbox.

Run from the dao_protocol directory::

    python truesight_dao_client/tests/test_e2e_subscription_webhook.py

Or via the console script (after pip install -e .):

    truesight-dao-e2e-subscription-webhook

Flags:
    --dry-run          Print what would be done without calling Stripe or SSH
    --beta-host HOST   Beta box hostname/IP (default: 54.162.175.189)
    --beta-key-path PATH  SSH key path (default: ~/.ssh/dao-protocol-beta-key)
    --stripe-key KEY   Stripe test secret key (default: from env STRIPE_TEST_SECRET_KEY)

Exit code: 0 = all checks passed, 1 = any check failed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Defaults
DEFAULT_BETA_HOST = "54.162.175.189"
DEFAULT_BETA_KEY = os.path.expanduser("~/.ssh/dao-protocol-beta-key")
WEBHOOK_URL = "https://beta.edgar.truesight.me/stripe/subscription_webhook"


def _stripe_api(method: str, path: str, data: dict | None = None, api_key: str = "") -> dict:
    """Call the Stripe REST API and return parsed JSON."""
    import urllib.request
    import urllib.error

    url = f"https://api.stripe.com/v1/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = urllib.parse.urlencode(data or {}).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        logger.error("Stripe API error %s: %s", e.code, err_body)
        return {"error": True, "status": e.code, "body": err_body}


def step(name: str, dry_run: bool = False) -> bool:
    """Decorator-like helper: print step header, return False if dry_run."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP: %s", name)
    logger.info("=" * 60)
    if dry_run:
        logger.info("[DRY RUN] Would execute this step.")
        return False
    return True


def check_beta_logs(beta_host: str, beta_key: str, search_term: str, timeout_secs: int = 30) -> bool:
    """SSH into the beta box and search systemd logs for a term."""
    cmd = [
        "ssh", "-i", beta_key,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        f"ubuntu@{beta_host}",
        f"sudo journalctl -u dao-protocol-beta --since '5 minutes ago' --no-pager 2>&1 | grep -i '{search_term}' || true",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_secs)
        if result.returncode == 0 and result.stdout.strip():
            logger.info("Found in beta logs: %s", result.stdout.strip()[:200])
            return True
        else:
            logger.warning("Not found in beta logs. stdout: %s", result.stdout.strip()[:200])
            return False
    except subprocess.TimeoutExpired:
        logger.warning("SSH timed out checking beta logs")
        return False
    except Exception as e:
        logger.warning("SSH error: %s", e)
        return False


def run_e2e(args: argparse.Namespace) -> int:
    """Run the E2E test. Returns 0 on success, 1 on failure."""
    api_key = args.stripe_key or os.environ.get("STRIPE_TEST_SECRET_KEY", "")
    if not api_key:
        logger.error("No Stripe test key provided. Set STRIPE_TEST_SECRET_KEY or pass --stripe-key")
        return 1

    dry_run = args.dry_run
    beta_host = args.beta_host
    beta_key = args.beta_key_path

    created_resources: dict = {}
    all_passed = True

    # ── Step 1: Create a test product ──
    if step("Create test product", dry_run):
        product_name = f"E2E Test Product {uuid.uuid4().hex[:8]}"
        resp = _stripe_api("POST", "products", {"name": product_name}, api_key)
        if resp.get("error"):
            logger.error("Failed to create product")
            all_passed = False
        else:
            created_resources["product_id"] = resp["id"]
            logger.info("Created product: %s (%s)", resp["id"], product_name)

    # ── Step 2: Create a test price ($10/month) ──
    if step("Create test price ($10/month)", dry_run) and all_passed:
        resp = _stripe_api("POST", "prices", {
            "product": created_resources.get("product_id", ""),
            "unit_amount": "1000",
            "currency": "usd",
            "recurring[interval]": "month",
        }, api_key)
        if resp.get("error"):
            logger.error("Failed to create price")
            all_passed = False
        else:
            created_resources["price_id"] = resp["id"]
            logger.info("Created price: %s ($10/month)", resp["id"])

    # ── Step 3: Create a test customer ──
    if step("Create test customer", dry_run) and all_passed:
        customer_email = f"e2e-test-{uuid.uuid4().hex[:8]}@truesight.me"
        resp = _stripe_api("POST", "customers", {
            "email": customer_email,
            "description": "E2E test customer - will be deleted",
        }, api_key)
        if resp.get("error"):
            logger.error("Failed to create customer")
            all_passed = False
        else:
            created_resources["customer_id"] = resp["id"]
            created_resources["customer_email"] = customer_email
            logger.info("Created customer: %s (%s)", resp["id"], customer_email)

    # ── Step 4: Attach pm_card_visa payment method ──
    if step("Attach pm_card_visa payment method", dry_run) and all_passed:
        # Create a payment method first
        resp = _stripe_api("POST", "payment_methods", {
            "type": "card",
            "card[token]": "tok_visa",
        }, api_key)
        if resp.get("error"):
            logger.error("Failed to create payment method: %s", resp.get("body", ""))
            all_passed = False
        else:
            pm_id = resp["id"]
            created_resources["payment_method_id"] = pm_id
            logger.info("Created payment method: %s", pm_id)
            # Attach to customer
            attach_resp = _stripe_api("POST", f"payment_methods/{pm_id}/attach", {
                "customer": created_resources["customer_id"],
            }, api_key)
            if attach_resp.get("error"):
                logger.error("Failed to attach payment method")
                all_passed = False
            else:
                logger.info("Attached payment method to customer")
                # Set as default payment method on customer
                _stripe_api("POST", f"customers/{created_resources['customer_id']}", {
                    "invoice_settings[default_payment_method]": pm_id,
                }, api_key)

    # ── Step 5: Create subscription ──
    subscription_id = None
    if step("Create subscription (triggers invoice.paid webhook)", dry_run) and all_passed:
        resp = _stripe_api("POST", "subscriptions", {
            "customer": created_resources["customer_id"],
            "items[0][price]": created_resources["price_id"],
            "payment_behavior": "default_incomplete",
            "expand[]": ["latest_invoice", "pending_setup_intent"],
        }, api_key)
        if resp.get("error"):
            logger.error("Failed to create subscription: %s", resp.get("body", ""))
            all_passed = False
        else:
            subscription_id = resp["id"]
            created_resources["subscription_id"] = subscription_id
            logger.info("Created subscription: %s", subscription_id)
            logger.info("Status: %s", resp.get("status"))

    # ── Step 6: Wait for webhook delivery ──
    if step("Wait for webhook delivery + check beta logs", dry_run) and all_passed and subscription_id:
        logger.info("Waiting 15 seconds for Stripe to deliver webhook...")
        time.sleep(15)

        # Check beta box logs for the subscription ID
        found = check_beta_logs(beta_host, beta_key, subscription_id, timeout_secs=20)
        if found:
            logger.info("PASS: Webhook received and logged for subscription %s", subscription_id)
        else:
            logger.warning("Subscription ID not found in logs. Checking for any webhook activity...")
            # Broader search
            found_any = check_beta_logs(beta_host, beta_key, "stripe_subscription", timeout_secs=10)
            if found_any:
                logger.warning("Webhook module was invoked but subscription ID may differ")
                all_passed = False
            else:
                logger.warning("No webhook activity found in logs")
                all_passed = False

    # ── Step 7: Verify webhook endpoint returns 400 without signature ──
    if step("Verify unsigned POST returns 400", dry_run):
        import urllib.request
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=b'{"test":true}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode()
                logger.warning("Expected 400 but got %s: %s", resp.status, body)
                all_passed = False
        except urllib.error.HTTPError as e:
            if e.code == 400:
                logger.info("PASS: Unsigned POST returned 400 as expected")
            else:
                logger.warning("Expected 400 but got %s", e.code)
                all_passed = False

    # ── Cleanup ──
    if step("Cleanup: cancel subscription + delete customer + product", dry_run):
        # Cancel subscription
        if "subscription_id" in created_resources:
            resp = _stripe_api("POST", f"subscriptions/{created_resources['subscription_id']}",
                               {"cancel_at_period_end": "true"}, api_key)
            if resp.get("error"):
                logger.warning("Failed to cancel subscription: %s", resp.get("body", ""))
            else:
                logger.info("Subscription cancellation initiated")

        # Delete customer
        if "customer_id" in created_resources:
            resp = _stripe_api("DELETE", f"customers/{created_resources['customer_id']}", {}, api_key)
            if resp.get("error"):
                logger.warning("Failed to delete customer: %s", resp.get("body", ""))
            else:
                logger.info("Deleted customer %s", created_resources["customer_id"])

        # Delete product (also deletes the price)
        if "product_id" in created_resources:
            resp = _stripe_api("DELETE", f"products/{created_resources['product_id']}", {"type": "good"}, api_key)
            if resp.get("error"):
                logger.warning("Failed to delete product: %s", resp.get("body", ""))
            else:
                logger.info("Deleted product %s (price deleted automatically)", created_resources["product_id"])

    # ── Summary ──
    logger.info("")
    logger.info("=" * 60)
    if all_passed:
        logger.info("RESULT: ALL CHECKS PASSED")
        return 0
    else:
        logger.warning("RESULT: SOME CHECKS FAILED")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2E test: Stripe subscription webhook against beta sandbox"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    parser.add_argument("--beta-host", default=DEFAULT_BETA_HOST, help=f"Beta box host (default: {DEFAULT_BETA_HOST})")
    parser.add_argument("--beta-key-path", default=DEFAULT_BETA_KEY, help=f"SSH key path (default: {DEFAULT_BETA_KEY})")
    parser.add_argument("--stripe-key", default="", help="Stripe test secret key (default: STRIPE_TEST_SECRET_KEY env)")
    args = parser.parse_args()

    sys.exit(run_e2e(args))


if __name__ == "__main__":
    main()
