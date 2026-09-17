"""[PAYOUT EVENT] catalog regression pin (CRF_ANAPU_SUNMINT_COHORT_PROPOSAL.md §12).

The payout event is the missing third leg of the tree-planting cycle (funding leg via
[SALES EVENT] -> liability; fulfilment via tree_planting; disbursement = this event).
It is registered in `events_catalog.json` (served at GET /events-catalog) so the DApp
emitter (`payout-event-utils.js`) and `lookup_event_docs` agree on one label contract.

These labels MUST match `buildAttributes()` in dapp_beta/payout-event-utils.js verbatim
and in order — the payload is signed verbatim, so label order is part of the contract.
Delivery (dispatch routing + the GAS sink) is Q3/Q4 and intentionally NOT wired here.
"""

from __future__ import annotations

import json
from pathlib import Path

_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "truesight_dao_client"
    / "server"
    / "data"
    / "events_catalog.json"
)

# Exact emitter order — see dapp_beta/payout-event-utils.js buildAttributes().
EMITTER_LABELS = [
    "Program",
    "Amount",
    "Currency",
    "Paid At",
    "Bank Ref Type",
    "Bank Ref",
    "Recipient",
    "Recipient PK Hash",
    "Tree Planting IDs",
    "Status",
    "Receipt URL",
    "Submission Source",
]


def _entry() -> dict:
    return json.loads(_CATALOG_PATH.read_text())["events"]["PAYOUT EVENT"]


def test_payout_event_is_catalogued():
    assert "PAYOUT EVENT" in json.loads(_CATALOG_PATH.read_text())["events"]


def test_payout_event_labels_match_emitter_order():
    assert _entry()["canonical_labels"] == EMITTER_LABELS


def test_payout_event_required_fields():
    assert _entry()["required_fields"] == [
        "Program",
        "Amount",
        "Currency",
        "Paid At",
        "Bank Ref",
        "Recipient",
    ]


def test_payout_event_has_no_raw_pix_label():
    """Privacy contract: no raw-PIX field may ever appear in the catalog entry."""
    assert not any("pix" in lbl.lower() for lbl in _entry()["canonical_labels"])


def test_payout_event_points_at_the_emitter_page():
    assert _entry()["dapp_page"] == "report_payout_event.html"
