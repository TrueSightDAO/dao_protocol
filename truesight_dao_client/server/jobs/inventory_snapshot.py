"""Port of Rails `AgroverseInventorySnapshotPublishWorker` — refresh the public Agroverse
inventory JSON after a ledger-affecting event (e.g. ASSET RECEIPT). It's a `GET ?action=&token=`
to the inventory GAS web app (corrected: the Rails worker is a GET with a token param, not a
POST). Skips quietly when the URL/secret aren't configured (same as Rails / gate-off)."""

from __future__ import annotations

import logging

import requests

from ..config import get_settings

logger = logging.getLogger("dao_protocol.inventory_snapshot")
_VALID_ACTIONS = {"publishInventorySnapshot", "recalculateAndPublishInventory"}
_TIMEOUT = 360


def publish() -> bool:
    s = get_settings()
    base = (s.agroverse_inventory_gas_webapp_url or "").strip()
    secret = (s.agroverse_inventory_publish_secret or "").strip()
    action = (s.agroverse_inventory_gas_action or "recalculateAndPublishInventory").strip()
    if not base or not secret:
        logger.info("inventory snapshot skipped: GAS url/secret not configured")
        return False
    if action not in _VALID_ACTIONS:
        logger.error("invalid inventory GAS action %r", action)
        return False
    try:
        sep = "&" if "?" in base else "?"
        resp = requests.get(f"{base}{sep}action={action}&token={secret}", timeout=_TIMEOUT)
        if resp.ok:
            logger.info("inventory snapshot ok action=%s", action)
            return True
        logger.error("inventory snapshot HTTP %s", resp.status_code)
        return False
    except requests.RequestException as exc:
        logger.warning("inventory snapshot failed: %s", exc)
        return False
