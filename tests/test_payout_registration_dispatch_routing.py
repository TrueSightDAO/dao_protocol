"[PAYOUT REGISTRATION] catalog + dispatch-routing regression.

The registration event (CRF_ANAPU_SUNMINT_COHORT_PROPOSAL.md SS11) is a planter
DECLARING the PIX key to be paid at -- the sibling of [PAYOUT EVENT] (SS12), which
is the RECEIPT of a transfer. It must be registered in the canonical events catalog
(served at GET /events-catalog, consumed by `lookup_event_docs`) AND routed to its
own GAS webhook action.

Previously the tag was intentionally left unrouted (relying on the GAS hourly
safety-net cron). That left the private `cfr program` sink with NO edge-triggered
path: a registration only landed if the hourly cron happened to run AND succeed.
Routing it here makes delivery edge-triggered; the cron remains the backstop.

Spec: agentic_ai_context/plans/CRF_ANAPU_SUNMINT_COHORT_PROPOSAL.md SS11.
"""

from __future__ import annotations

import json
from pathlib import Path

from truesight_dao_client.server import dispatch

_CATALOG = Path(dispatch.__file__).resolve().parent / "data" / "events_catalog.json"

TAG = "[PAYOUT REGISTRATION]"
ENV_KEY = "PAYOUT_REGISTRATION_PROCESSING"
ACTION = "processPayoutRegistrationsFromTelegramChatLogs"


def _route_for(tag):
    for tags, targets, enqueue in dispatch.ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        if tag in tag_tuple:
            return targets, enqueue
    raise AssertionError(f"no routing entry for {tag}")


def _catalog():
    return json.loads(_CATALOG.read_text())


def test_payout_registration_registered_in_catalog():
    ev = _catalog()["events"]["PAYOUT REGISTRATION"]
    assert ev["category"] == "Contribution & Finance"
    assert ev["dapp_page"] == "payout_registration.html"
    for field in ("Planting Identity (pk_hash)", "Program", "PIX key"):
        assert field in ev["canonical_labels"], field
        assert field in ev["required_fields"], field


def test_payout_registration_routes_to_its_own_handler():
    targets, enqueue = _route_for(TAG)
    assert targets == [(ENV_KEY, ACTION)]
    assert enqueue is False


def test_payout_registration_is_not_conflated_with_payout_event():
    """A recipient declaration is not a transfer receipt - distinct tag, env key, handler."""
    registration = _route_for(TAG)[0]
    event = _route_for("[PAYOUT EVENT]")[0]
    assert registration != event
    assert registration[0][0] != event[0][0]
    assert registration[0][1] != event[0][1]


def test_payout_event_routing_does_not_match_registration_text():
    """First-match-wins: a `[PAYOUT EVENT]` route must never fire on a registration."""
    targets, _ = _route_for("[PAYOUT EVENT]")
    assert targets == [("PAYOUT_PROCESSING", "processPayoutEventsFromTelegramChatLogs")]


def test_payout_registration_dedicated_env_key_overrides_fallback(monkeypatch):
    """A dedicated env var wins over the shared-deployment fallback when both are set."""
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_PROCESSING", "https://shared.test/exec"
    )
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_REGISTRATION_PROCESSING", "https://own.test/exec"
    )
    assert dispatch._webhook_url(ENV_KEY) == "https://own.test/exec"


def test_payout_registration_falls_back_to_shared_deployment(monkeypatch):
    """With no dedicated env var, registration reuses the payout deployment URL."""
    monkeypatch.delenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_REGISTRATION_PROCESSING", raising=False
    )
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_PROCESSING", "https://shared.test/exec"
    )
    assert dispatch._webhook_url(ENV_KEY) == "https://shared.test/exec"


def test_payout_registration_fires_webhook(monkeypatch):
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_PROCESSING", "https://shared.test/exec"
    )
    seen = {}
    monkeypatch.setattr(
        dispatch.webhook_trigger,
        "trigger",
        lambda url, action: seen.update(url=url, action=action) or True,
    )
    dispatch.dispatch_event(
        "[PAYOUT REGISTRATION]\n- Planting Identity (pk_hash): pk-abc123\n--------\nSig"
    )
    assert seen.get("action") == ACTION
    assert seen.get("url") == "https://shared.test/exec"


def test_payout_registration_does_not_enqueue_inventory_snapshot(monkeypatch):
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PAYOUT_PROCESSING", "https://shared.test/exec"
    )
    called = {}
    monkeypatch.setattr(dispatch.webhook_trigger, "trigger", lambda *a, **k: True)
    monkeypatch.setattr(
        dispatch.inventory_snapshot, "publish", lambda: called.update(p=True)
    )
    dispatch.dispatch_event(
        "[PAYOUT REGISTRATION]\n- Planting Identity (pk_hash): pk-abc123"
    )
    assert called.get("p") is None
