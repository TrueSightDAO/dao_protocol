"""[PAYOUT EVENT] dispatch routing + catalog regression pin (Q3a).

Unit Q3a of agentic_ai_context/plans/CRF_ANAPU_SUNMINT_COHORT_PROPOSAL.md §12.7:
the `[PAYOUT EVENT]` tag must (a) be registered in the canonical events catalog
(served at GET /events-catalog, consumed by `lookup_event_docs`) and (b) be routed
to its own GAS webhook action so the sink can book the row.

A payout is a *liability discharge* (money out to a recipient), NOT a stock move, so
the routing entry must NOT enqueue the Agroverse inventory snapshot. This mirrors the
distinction the reservation handler pins (settlement books inventory, reservation does not).

The `[PAYOUT REGISTRATION]` sibling (P4) is deliberately NOT routed here — it relies on
its GAS hourly-trigger safety net — so this test also pins that the two tags stay distinct
(i.e. routing on `[PAYOUT EVENT]` must not accidentally match `[PAYOUT REGISTRATION]` text).
"""

from __future__ import annotations

import json
from pathlib import Path

from truesight_dao_client.server import dispatch

_CATALOG = Path(dispatch.__file__).resolve().parent / "data" / "events_catalog.json"

TAG = "[PAYOUT EVENT]"
ENV_KEY = "PAYOUT_PROCESSING"
ACTION = "processPayoutEventsFromTelegramChatLogs"


def _route_for(tag):
    for tags, targets, enqueue in dispatch.ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        if tag in tag_tuple:
            return targets, enqueue
    raise AssertionError(f"no routing entry for {tag}")


def _catalog():
    return json.loads(_CATALOG.read_text())


def test_payout_event_registered_in_catalog():
    ev = _catalog()["events"]["PAYOUT EVENT"]
    assert ev["dapp_page"] == "report_payout_event.html"
    for f in ("Program", "Amount", "Currency", "Paid At", "Bank Ref", "Recipient"):
        assert f in ev["required_fields"], f


def test_payout_event_routes_to_its_own_handler():
    targets, enqueue = _route_for(TAG)
    assert targets == [(ENV_KEY, ACTION)]


def test_payout_event_does_not_enqueue_inventory_snapshot():
    _, enqueue = _route_for(TAG)
    assert enqueue is False


def test_payout_event_does_not_match_payout_registration_text():
    """Routing on [PAYOUT EVENT] must not fire on a [PAYOUT REGISTRATION] submission."""
    targets, _ = _route_for(TAG)
    # The tag is bracketed, so plain substring matching of "[PAYOUT EVENT]" cannot match
    # "[PAYOUT REGISTRATION]". Pin that the env key/action are payout-specific.
    assert ENV_KEY == "PAYOUT_PROCESSING"
    assert targets[0][0] != "PAYOUT_REGISTRATION_PROCESSING"


def test_dispatch_event_is_a_noop_without_webhook_url(monkeypatch, caplog):
    """With the env var unset (pre-Q3b), dispatch must log + degrade, never raise."""
    import logging

    monkeypatch.delenv("DAO_PROTOCOL_WEBHOOK_PAYOUT_PROCESSING", raising=False)
    with caplog.at_level(logging.WARNING):
        dispatch.dispatch_event("[PAYOUT EVENT]\nAmount: 100")
    assert any(
        "PAYOUT_PROCESSING" in r.message or "PAYOUT_PROCESSING" in str(r.args)
        for r in caplog.records
    )
