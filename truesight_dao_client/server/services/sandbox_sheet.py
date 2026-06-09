"""Placeholder SANDBOX fulfillment-queue sheet service.

Writes rows to a Google Sheet tab for tracking subscription events (checkout,
invoice paid/failed, subscription deleted). Currently logs to stdout; the actual
sheet integration can be wired when the SANDBOX sheet ID is configured.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def write_subscription_row(
    customer_email: str,
    subscription_id: str,
    invoice_id: str = "",
    status: str = "active",
) -> None:
    """Write/update a row in the SANDBOX fulfillment-queue sheet.

    Placeholder implementation: logs to stdout.
    """
    msg = f"SANDBOX sheet: customer_email={customer_email} subscription_id={subscription_id} invoice_id={invoice_id} status={status}"
    logger.info(msg)
    print(msg, flush=True)


def mark_subscription_failed(subscription_id: str, invoice_id: str = "") -> None:
    """Mark a subscription row as failed in the SANDBOX sheet."""
    msg = f"SANDBOX sheet: marking subscription_id={subscription_id} invoice_id={invoice_id} as failed"
    logger.info(msg)
    print(msg, flush=True)


def mark_subscription_cancelled(subscription_id: str) -> None:
    """Mark a subscription row as cancelled in the SANDBOX sheet."""
    msg = f"SANDBOX sheet: marking subscription_id={subscription_id} as cancelled"
    logger.info(msg)
    print(msg, flush=True)
