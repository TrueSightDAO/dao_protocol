"""[RESERVATION EVENT] / [RESERVATION SETTLEMENT EVENT] registration regression.

Pins unit 2 of agentic_ai_context/RESERVATION_EVENT_SPEC.md: both reservation events must be
registered in the canonical events catalog (served at edgar.truesight.me/events-catalog) AND
routed to their own distinct GAS webhook actions.

The settlement tag is the derived event (fires second), so it must not be conflated with the
reservation tag. Settlement books the inventory -1, so it must enqueue the inventory snapshot;
reservation books no inventory row, so it must not.

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


def test_reservation_event_registered_in_catalog():
    ev = _catalog()["events"]["RESERVATION EVENT"]
    assert ev["category"] == "Inventory & Supply Chain"
    assert ev["dapp_page"] == "report_reservation.html"
    for f in ("Buyer", "Buyer Email", "QR Code", "Payment Collected By", "Sale Price"):
        assert f in ev["canonical_labels"], f
    for f in ("Buyer", "QR Code", "Sale Price"):
        assert f in ev["required_fields"], f


def test_reservation_settlement_event_registered_in_catalog():
    ev = _catalog()["events"]["RESERVATION SETTLEMENT EVENT"]
    assert ev["category"] == "Inventory & Supply Chain"
    assert ev["dapp_page"] == "report_reservation_settlement.html"
    for f in ("QR Code", "Buyer Email"):
        assert f in ev["canonical_labels"], f
    assert ev["required_fields"] == ["QR Code"]


def test_reservation_routes_to_reservation_handler():
    targets, enqueue = _route_for("[RESERVATION EVENT]")
    assert targets == [("RESERVATION_PROCESSING", "processReservationTelegramLogs")]
    assert enqueue is False


def test_reservation_settlement_routes_to_settlement_handler():
    targets, enqueue = _route_for("[RESERVATION SETTLEMENT EVENT]")
    assert targets == [
        (
            "RESERVATION_SETTLEMENT_PROCESSING",
            "processReservationSettlementTelegramLogs",
        )
    ]
    assert enqueue is True


def test_reservation_tags_are_not_conflated():
    reservation = _route_for("[RESERVATION EVENT]")[0]
    settlement = _route_for("[RESERVATION SETTLEMENT EVENT]")[0]
    assert reservation != settlement
    assert reservation[0][0] != settlement[0][0]  # distinct env keys
    assert reservation[0][1] != settlement[0][1]  # distinct GAS action names


def test_settlement_enqueues_inventory_snapshot_reservation_does_not():
    # Settlement books the inventory -1, so the public inventory JSON must refresh.
    # Reservation books no inventory row, so it must NOT trigger a snapshot publish.
    assert _route_for("[RESERVATION SETTLEMENT EVENT]")[1] is True
    assert _route_for("[RESERVATION EVENT]")[1] is False
