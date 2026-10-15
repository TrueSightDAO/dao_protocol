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

# Defaults, env-overridable via Settings. A cold-started Apps Script call can exceed the historical
# 30 s ceiling (observed 2026-10-15 on `processTelegramChatLogs`: attempts 1-2 timed out at 30 s,
# attempt 3 succeeded). Tunable so operators can widen the ceiling without a code change.
_DEFAULT_TIMEOUT = 45
_DEFAULT_MAX_ATTEMPTS = 4


def _tuning() -> tuple[int, int]:
    """Return (timeout_s, max_attempts) from Settings, falling back to module defaults.

    Settings import is best-effort: a config failure must never break a best-effort webhook.
    """
    try:
        from ..config import get_settings

        settings = get_settings()
        return int(settings.webhook_timeout_s), int(settings.webhook_max_attempts)
    except Exception:  # noqa: BLE001 — best-effort; fall back to defaults
        return _DEFAULT_TIMEOUT, _DEFAULT_MAX_ATTEMPTS


def _run(webhook_url: str, params: dict, label: str) -> bool:
    """GET webhook_url with `params`. Returns True on a 2xx, False otherwise. Best-effort:
    retries only on network/timeout errors (not on non-2xx)."""
    timeout, max_attempts = _tuning()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(webhook_url, params=params, timeout=timeout)
            if resp.ok:
                logger.info("webhook ok: %s (%s)", label, webhook_url)
                return True
            logger.warning(
                "webhook non-2xx %s: %s (%s) — cron fallback",
                resp.status_code,
                label,
                webhook_url,
            )
            return False  # don't retry non-2xx (matches Rails)
        except requests.RequestException as exc:
            logger.warning(
                "webhook attempt %d/%d failed: %s — %s", attempt, max_attempts, label, exc
            )
            if attempt < max_attempts:
                time.sleep(2 * attempt)
    return False


def trigger(webhook_url: str, action: str, description: str | None = None) -> bool:
    """GET webhook_url?action=<action>. Returns True on a 2xx, False otherwise. Best-effort:
    retries only on network/timeout errors (not on non-2xx)."""
    return _run(webhook_url, {"action": action}, description or action)


def trigger_with_params(webhook_url: str, params: dict, description: str | None = None) -> bool:
    """GET webhook_url with arbitrary query params. Same retry logic as trigger()."""
    return _run(webhook_url, params, description or str(params))
