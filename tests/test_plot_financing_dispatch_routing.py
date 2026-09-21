"""[PLOT FINANCING EVENT] registration regression.

Pins the unit that adds a dedicated ADVANCE event for financing N trees on a SunMint plot
(agentic_ai_context/plans/SUNMINT_FARMER_SETTLEMENT_AND_BATCH_LINK_PLAN.md).

The tag must be registered in the canonical events catalog (served at
edgar.truesight.me/events-catalog) AND routed to its own GAS webhook action, so the event is
discoverable (lookup_event_docs / DApp) rather than shipping silently as routed-but-uncatalogued.

A financing event mints a POOL INVENTORY literal ('Cacao Tree Planted - Unassigned'), not a
physical stock move, so it must NOT enqueue the inventory snapshot.

Lives here (dao_protocol) because this repo is where the `dispatch` module and its pytest suite
actually live/run.
"""

from __future__ import annotations

import json
from pathlib import Path

from truesight_dao_client.server import dispatch

_CATALOG = Path(dispatch.__file__).resolve().parent / "data" / "events_catalog.json"


def _route_for(tag):
    for tags, targets, enqueue in dispatch.ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        if tag in tag_tuple:
            return targets, enqueue
    raise AssertionError(f"no routing entry for {tag}")


def _catalog():
    return json.loads(_CATALOG.read_text())


def test_plot_financing_registered_in_catalog():
    ev = _catalog()["events"]["PLOT FINANCING EVENT"]
    assert ev["category"] == "Contribution & Finance"
    assert ev["dapp_page"] == "report_plot_financing.html"
    for f in ("Plot ID", "Farmer", "Amount", "Currency", "Tree Count"):
        assert f in ev["canonical_labels"], f
        assert f in ev["required_fields"], f


def test_plot_financing_routes_to_its_own_handler():
    targets, enqueue = _route_for("[PLOT FINANCING EVENT]")
    assert targets == [
        (
            "PLOT_FINANCING_PROCESSING",
            "processPlotFinancingEventsFromTelegramChatLogs",
        )
    ]
    assert enqueue is False


def test_plot_financing_is_not_conflated_with_payout():
    """An advance is not a settlement - distinct tag, env key, and handler."""
    financing = _route_for("[PLOT FINANCING EVENT]")[0]
    payout = _route_for("[PAYOUT EVENT]")[0]
    assert financing != payout
    assert financing[0][0] != payout[0][0]
    assert financing[0][1] != payout[0][1]


def test_plot_financing_does_not_enqueue_inventory_snapshot(monkeypatch):
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PLOT_FINANCING_PROCESSING", "https://example.test/exec"
    )
    called = {}
    monkeypatch.setattr(dispatch.webhook_trigger, "trigger", lambda *a, **k: True)
    monkeypatch.setattr(
        dispatch.inventory_snapshot, "publish", lambda: called.update(p=True)
    )
    dispatch.dispatch_event("[PLOT FINANCING EVENT]\n- Plot ID: RM-P1")
    assert called.get("p") is None


def test_plot_financing_fires_webhook(monkeypatch):
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_PLOT_FINANCING_PROCESSING", "https://example.test/exec"
    )
    seen = {}
    monkeypatch.setattr(
        dispatch.webhook_trigger,
        "trigger",
        lambda url, action: seen.update(url=url, action=action) or True,
    )
    dispatch.dispatch_event(
        "[PLOT FINANCING EVENT]\n- Plot ID: RM-P1\n- Tree Count: 500\n--------\nSig"
    )
    assert seen.get("action") == "processPlotFinancingEventsFromTelegramChatLogs"
    assert seen.get("url") == "https://example.test/exec"
