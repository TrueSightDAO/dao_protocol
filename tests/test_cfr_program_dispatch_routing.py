"""[TREE PLANTING EVENT] / [TREE GROWTH MONITORING EVENT] / [FARM BOUNDARY EVIDENCE EVENT]
additive CFR-program mirror regression.

Closes the SS11.5 wiring step of agentic_ai_context/CRF_ANAPU_SUNMINT_COHORT_PROPOSAL.md:
CFR-origin (cfr.truesight.me) tree/monitoring/plot submissions must ALSO be mirrored into the
private `cfr program` sheet (GAS action `processCfrProgramSubmissionsFromTelegramChatLogs`).

THE INVARIANT THIS FILE PINS (Gary, 2026-09-24): the wiring is ADDITIVE. `dispatch_event`
fires EVERY target of a matched entry, so the CFR target must be APPENDED as a SECOND target
-- the pre-existing SunMint target (which feeds the public `SunMint Tree Planting` tab) must
stay. A future "cleanup" that replaces the SunMint target with the CFR one would silently take
the public tree-planting tab dark. These tests fail loudly if that ever happens.

Lives here (dao_protocol) because this repo is where the `dispatch` module and its pytest
suite actually live/run.
"""

from __future__ import annotations

from truesight_dao_client.server import dispatch

_CFR_TARGET = (
    "CFR_PROGRAM_REGISTRATION_PROCESSING",
    "processCfrProgramSubmissionsFromTelegramChatLogs",
)


def _route_for(tag):
    for tags, targets, enqueue in dispatch.ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        if tag in tag_tuple:
            return targets, enqueue
    raise AssertionError(f"no routing entry for {tag}")


def test_tree_planting_keeps_sunmint_target_and_adds_cfr():
    targets, enqueue = _route_for("[TREE PLANTING EVENT]")
    assert ("TREE_PLANTING_PROCESSING", "processTreePlantingTelegramLogs") in targets
    assert _CFR_TARGET in targets
    assert enqueue is False


def test_tree_growth_monitoring_keeps_sunmint_target_and_adds_cfr():
    targets, enqueue = _route_for("[TREE GROWTH MONITORING EVENT]")
    assert (
        "TREE_GROWTH_MONITORING",
        "processTreeGrowthMonitoringFromTelegramChatLogs",
    ) in targets
    assert _CFR_TARGET in targets
    assert enqueue is False


def test_farm_boundary_evidence_keeps_sunmint_target_and_adds_cfr():
    targets, enqueue = _route_for("[FARM BOUNDARY EVIDENCE EVENT]")
    assert (
        "FARM_BOUNDARY_EVIDENCE",
        "processFarmBoundaryEvidenceFromTelegramChatLogs",
    ) in targets
    assert _CFR_TARGET in targets
    assert enqueue is False


def test_dispatch_event_fires_both_targets_for_tree_planting(monkeypatch):
    """The whole point: one [TREE PLANTING EVENT] must call BOTH webhooks."""
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_TREE_PLANTING_PROCESSING", "https://sunmint.test/exec"
    )
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_CFR_PROGRAM_REGISTRATION_PROCESSING",
        "https://cfr.test/exec",
    )
    seen = []
    monkeypatch.setattr(
        dispatch.webhook_trigger,
        "trigger",
        lambda url, action: seen.append((url, action)) or True,
    )
    dispatch.dispatch_event(
        "[TREE PLANTING EVENT]\n- Latitude: 1\n- Longitude: 2\n--------\nSig"
    )
    actions = {a for _, a in seen}
    assert "processTreePlantingTelegramLogs" in actions
    assert "processCfrProgramSubmissionsFromTelegramChatLogs" in actions
    urls = {u for u, _ in seen}
    assert "https://sunmint.test/exec" in urls
    assert "https://cfr.test/exec" in urls


def test_cfr_target_absent_degrades_gracefully(monkeypatch):
    """CFR env var unset -> SunMint still fires, CFR is skipped (not fatal)."""
    monkeypatch.setenv(
        "DAO_PROTOCOL_WEBHOOK_TREE_PLANTING_PROCESSING", "https://sunmint.test/exec"
    )
    monkeypatch.delenv(
        "DAO_PROTOCOL_WEBHOOK_CFR_PROGRAM_REGISTRATION_PROCESSING", raising=False
    )
    seen = []
    monkeypatch.setattr(
        dispatch.webhook_trigger,
        "trigger",
        lambda url, action: seen.append((url, action)) or True,
    )
    dispatch.dispatch_event("[TREE PLANTING EVENT]\n- Latitude: 1\n- Longitude: 2")
    assert [a for _, a in seen] == ["processTreePlantingTelegramLogs"]
