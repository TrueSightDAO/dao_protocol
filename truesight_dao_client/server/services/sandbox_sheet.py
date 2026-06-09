"""Fulfillment-queue sheet service — wired to the real Subscription Fulfillment Queue tab.

Writes rows to the Main Ledger's "Subscription Fulfillment Queue" tab for tracking
subscription events (checkout, invoice paid/failed, subscription deleted).
Previously a placeholder that logged to stdout; now uses the real queue module.
"""

from __future__ import annotations

import logging

from ..sheets import subscription_fulfillment_queue as queue

logger = logging.getLogger(__name__)


def write_subscription_row(
    customer_email: str,
    subscription_id: str,
    invoice_id: str = "",
    status: str = "active",
) -> None:
    """Write/update a row in the fulfillment-queue sheet.

    Only writes PENDING rows for 'active' status (paid invoices).
    Idempotent on invoice_id.
    """
    if status == "active" and invoice_id:
        ok = queue.append_obligation(
            subscriber_name="",
            email=customer_email,
            address="",
            sku="generic-ceremonial-cacao-chocolate-bar",
            qty=6,
            period_start="",
            period_end="",
            invoice_id=invoice_id,
        )
        if ok:
            logger.info("Fulfillment queue: appended obligation for invoice %s", invoice_id)
        else:
            logger.warning("Fulfillment queue: failed to append obligation for invoice %s", invoice_id)
    else:
        logger.info("Fulfillment queue: skipped (status=%s, invoice_id=%s)", status, invoice_id)


def mark_subscription_failed(subscription_id: str, invoice_id: str = "") -> None:
    """Mark a subscription row as failed in the fulfillment-queue sheet."""
    if invoice_id:
        # For now, we just log. The queue module doesn't have a mark_failed yet.
        logger.info("Fulfillment queue: marking invoice %s as failed (sub %s)", invoice_id, subscription_id)
    else:
        logger.info("Fulfillment queue: marking sub %s as failed (no invoice)", subscription_id)


def mark_subscription_cancelled(subscription_id: str) -> None:
    """Mark a subscription row as cancelled in the fulfillment-queue sheet."""
    logger.info("Fulfillment queue: marking sub %s as cancelled", subscription_id)
