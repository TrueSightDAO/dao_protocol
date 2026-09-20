"""[PAYOUT EVENT] farmer-settlement semantics pin (plan PR4b).

Unit PR4b of agentic_ai_context/plans/SUNMINT_FARMER_SETTLEMENT_AND_BATCH_LINK_PLAN.md.

Plan PR4 chose to REUSE `[PAYOUT EVENT]` rather than introduce a new `[FARMER PAYMENT
EVENT]` tag: a payout carrying a `tree_planting_id` IS the farmer-payment event (SS0.10).
This module pins the two facts that make that reuse correct - and that keep it from
silently regressing:

  1. The tag is ALREADY routed to its single sink, so no new routing entry is needed.
     (Adding an unrouted/uncatalogued `[FARMER PAYMENT EVENT]` tag would be drift.)
  2. The sink-side settlement semantics (SS0.11 cross-ledger transfer / SS1.2 Path B pool
     settlement, and the fail-closed no-attribution rule) are DOCUMENTED in the catalog,
     so `lookup_event_docs('PAYOUT EVENT')` surfaces them to a governor.
"""

from __future__ import annotations

import json
from pathlib import Path

from truesight_dao_client.server import dispatch

_CATALOG = Path(dispatch.__file__).resolve().parent / "data" / "events_catalog.json"
TAG = "[PAYOUT EVENT]"


def _entry() -> dict:
    return json.loads(_CATALOG.read_text())["events"]["PAYOUT EVENT"]


def test_payout_event_is_the_only_payout_route():
    """A tree-id-bearing payout reuses this route; no separate farmer-payment tag exists."""
    routed = []
    for tags, targets, _ in dispatch.ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        for tag in tag_tuple:
            if "PAYOUT" in tag.strip().upper():
                routed.append(tag)
    assert routed == [TAG], f"unexpected payout-family routes: {routed}"
    assert not any("FARMER" in t.upper() for t in routed)


def test_tree_planting_ids_is_part_of_the_label_contract():
    """The join key must remain a canonical label - it is how the sink finds the SunMint row."""
    assert "Tree Planting IDs" in _entry()["canonical_labels"]


def test_settlement_semantics_are_documented():
    """lookup_event_docs must surface how a payout books as a farmer settlement."""
    desc = _entry()["description"].upper()
    assert "SETTLEMENT" in desc
    assert "FAIL-CLOSED" in desc or "FAIL CLOSED" in desc
    assert "LEDGER_NOT_BOOKED" in desc
    assert "COMMITTED" in desc
