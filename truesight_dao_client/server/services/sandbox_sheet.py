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
    logger.info(
        "SANDBOX sheet: customer_email=%s subscription_id=%s invoice_id=%s status=%s",
        customer_email,
        subscription_id,
        invoice_id,
        status,
    )


def mark_subscription_failed(subscription_id: str, invoice_id: str = "") -> None:
    """Mark a subscription row as failed in the SANDBOX sheet."""
    logger.info(
        "SANDBOX sheet: marking subscription_id=%s invoice_id=%s as failed",
        subscription_id,
        invoice_id,
    )


def mark_subscription_cancelled(subscription_id: str) -> None:
    """Mark a subscription row as cancelled in the SANDBOX sheet."""
    logger.info(
        "SANDBOX sheet: marking subscription_id=%s as cancelled",
        subscription_id,
    )
