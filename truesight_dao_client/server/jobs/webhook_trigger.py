"""Port of Rails `WebhookTriggerWorker#perform` — fire a GAS webhook (HTTP GET `?action=`).

The Rails worker uses a Redis lock to avoid duplicate concurrent processing and Sidekiq retries
on network errors. Here we run inside FastAPI BackgroundTasks (gate-off, non-user-visible), so we
do a couple of best-effort attempts and log; a non-success HTTP status is NOT retried (the GAS
cron is the fallback, same as Rails). If/when this path is ramped and needs durable retries +
cross-process locking, move it to arq/Redis.
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger("dao_protocol.webhook")
_TIMEOUT = 30
_MAX_ATTEMPTS = 3


def trigger(webhook_url: str, action: str, description: str | None = None) -> bool:
    """GET webhook_url?action=<action>. Returns True on a 2xx, False otherwise. Best-effort:
    retries only on network/timeout errors (not on non-2xx)."""
    label = description or action
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(webhook_url, params={"action": action}, timeout=_TIMEOUT)
            if resp.ok:
                logger.info("webhook ok: %s (%s)", label, webhook_url)
                return True
            logger.warning("webhook non-2xx %s: %s (%s) — cron fallback", resp.status_code, label, webhook_url)
            return False  # don't retry non-2xx (matches Rails)
        except requests.RequestException as exc:
            logger.warning("webhook attempt %d/%d failed: %s — %s", attempt, _MAX_ATTEMPTS, label, exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(2 * attempt)
    return False


def trigger_with_params(webhook_url: str, params: dict, description: str | None = None) -> bool:
    """GET webhook_url with arbitrary query params. Same retry logic as trigger()."""
    label = description or str(params)
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(webhook_url, params=params, timeout=_TIMEOUT)
            if resp.ok:
                logger.info("webhook ok: %s (%s)", label, webhook_url)
                return True
            logger.warning("webhook non-2xx %s: %s (%s) — cron fallback", resp.status_code, label, webhook_url)
            return False
        except requests.RequestException as exc:
            logger.warning("webhook attempt %d/%d failed: %s — %s", attempt, _MAX_ATTEMPTS, label, exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(2 * attempt)
    return False
