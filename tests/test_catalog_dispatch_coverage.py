"""Drift guard: every dispatch-routed event tag MUST have a catalog entry.

`events_catalog.json` is the single source of truth served at GET /events-catalog and
consumed by `lookup_event_docs` and the DApp. `dispatch.py` ROUTING is what actually
fires GAS webhooks. When a tag exists in ROUTING but not in the catalog, the event
*works* but is undiscoverable/undocumented -- and Edgar does not validate event names
against the catalog, so the drift ships silently.

This test makes that drift fail CI. History: 4 tags
(CURRENCY DEFINITION EVENT, PROGRAM REGISTRATION REQUEST, CONTRIBUTION REVIEW EVENT,
TREE PLANTING REJECT EVENT) were routed-but-uncatalogued until 2026-09-13.
"""

from __future__ import annotations

import json
from pathlib import Path

from truesight_dao_client.server import dispatch

_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "truesight_dao_client"
    / "server"
    / "data"
    / "events_catalog.json"
)

# Tags that are intentionally routed but NOT documented in the catalog.
# Keep this empty unless there is a deliberate, documented reason.
KNOWN_UNCATALOGUED: set[str] = set()


def _routing_tags() -> set[str]:
    """ROUTING tags are bracketed markers (``[SALES EVENT]``); catalog keys are bare."""
    tags: set[str] = set()
    for entry in dispatch.ROUTING:
        entry_tags = entry[0]
        if not isinstance(entry_tags, tuple):
            entry_tags = (entry_tags,)
        for tag in entry_tags:
            tags.add(tag.strip().strip("[]").strip())
    return tags


def _catalog() -> dict:
    return json.loads(_CATALOG_PATH.read_text())


def test_catalog_is_valid_json_with_int_version():
    data = _catalog()
    assert isinstance(data.get("version"), int)
    assert data["version"] >= 7  # bumped when the 4 missing tags were added
    assert isinstance(data.get("events"), dict) and data["events"]


def test_every_routed_tag_is_catalogued():
    catalogued = set(_catalog()["events"].keys())
    missing = (_routing_tags() - catalogued) - KNOWN_UNCATALOGUED
    assert not missing, (
        "dispatch.ROUTING tags missing from events_catalog.json: "
        f"{sorted(missing)} -- add them to the catalog (or, if deliberate, to "
        "KNOWN_UNCATALOGUED with a comment)."
    )


def test_previously_missing_tags_are_now_catalogued():
    """Regression pin for the 2026-09-13 gap."""
    for tag in (
        "CURRENCY DEFINITION EVENT",
        "PROGRAM REGISTRATION REQUEST",
        "CONTRIBUTION REVIEW EVENT",
        "TREE PLANTING REJECT EVENT",
    ):
        assert tag in _catalog()["events"], f"{tag} fell out of the catalog"


def test_catalog_entries_have_required_shape():
    for name, entry in _catalog()["events"].items():
        assert (
            isinstance(entry.get("canonical_labels"), list)
            and entry["canonical_labels"]
        ), f"{name}: canonical_labels must be a non-empty list"
        assert isinstance(entry.get("required_fields"), list), (
            f"{name}: required_fields must be a list"
        )
        assert entry.get("category"), f"{name}: category is required"
