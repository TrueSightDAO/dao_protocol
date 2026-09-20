"""Decision-0.5 batch allocation core (plan PR7).

Pins the *pure* allocation rule so a refactor can't silently change which QR gets
linked to which kind of target:

  * a distinct, not-yet-used owner email -> a photographed TREE (1:1);
  * a repeat email, or a blank email       -> a PLOT association.

Also pins the safety contract: ``--execute`` without ``--yes`` refuses and fires
nothing (the link event books ledger rows -> ledger-money gate).
"""

from __future__ import annotations

import truesight_dao_client.modules.batch_link_sunmint as m


def _qr(code, email="", sold="2026-01-01"):
    return m.SoldQr(qr_code=code, owner_email=email, sold_date=sold)


def _tree(mid, farmer="Ana"):
    return m.TreeUnit(submission_message_id=mid, contributor_name=farmer)


def _plot(pid, farmer="Farm X"):
    return m.Plot(plot_id=pid, contributor_name=farmer)


def _kinds(pairings):
    return [p.kind for p in pairings]


# ── allocation rule ──────────────────────────────────────────────────────────


def test_distinct_email_gets_a_tree():
    pairs, un = m.compute_allocations([_qr("Q1", "a@x.com")], [_tree("T1")], [])
    assert un == []
    assert len(pairs) == 1
    assert pairs[0].kind == "tree" and pairs[0].target_id == "T1"


def test_repeat_email_falls_back_to_plot():
    qrs = [_qr("Q1", "a@x.com"), _qr("Q2", "a@x.com")]
    pairs, un = m.compute_allocations(qrs, [_tree("T1"), _tree("T2")], [_plot("P1")])
    assert un == []
    assert _kinds(pairs) == ["tree", "plot"]
    assert pairs[0].target_id == "T1" and pairs[1].target_id == "P1"
    assert "repeat" in pairs[1].reason


def test_blank_email_gets_a_plot():
    pairs, un = m.compute_allocations([_qr("Q1", "")], [_tree("T1")], [_plot("P1")])
    assert un == []
    assert _kinds(pairs) == ["plot"]
    assert "no owner email" in pairs[0].reason


def test_trees_exhausted_falls_back_to_plot():
    qrs = [_qr("Q1", "a@x.com"), _qr("Q2", "b@x.com")]
    pairs, _un = m.compute_allocations(qrs, [_tree("T1")], [_plot("P1")])
    assert _kinds(pairs) == ["tree", "plot"]
    assert "no tree unit available" in pairs[1].reason


def test_no_target_left_leaves_qr_unallocated():
    pairs, un = m.compute_allocations(
        [_qr("Q1", "a@x.com"), _qr("Q2", "b@x.com")], [_tree("T1")], []
    )
    assert len(pairs) == 1 and [q.qr_code for q in un] == ["Q2"]


def test_available_units_caps_the_run():
    qrs = [_qr("Q1", "a@x.com"), _qr("Q2", "b@x.com")]
    pairs, un = m.compute_allocations(
        qrs, [_tree("T1"), _tree("T2")], [], available_units=1
    )
    assert len(pairs) == 1 and [q.qr_code for q in un] == ["Q2"]


def test_allocation_is_deterministic_on_sold_date_then_code():
    qrs = [
        _qr("Q3", "c@x.com", "2026-02-01"),
        _qr("Q1", "a@x.com", "2026-01-01"),
        _qr("Q2", "b@x.com", "2026-01-01"),
    ]
    pairs, _ = m.compute_allocations(qrs, [_tree("T1"), _tree("T2"), _tree("T3")], [])
    assert [p.qr_code for p in pairs] == ["Q1", "Q2", "Q3"]


def test_a_plot_absorbs_many_bags_1_to_1():
    qrs = [_qr(f"Q{i}", "same@x.com") for i in range(3)]
    pairs, un = m.compute_allocations(qrs, [], [_plot("P1")])
    # one distinct email took the only tree; with no trees, all three hit plots
    assert un == [] and len(pairs) == 3


# ── attribute contract ───────────────────────────────────────────────────────


def test_tree_pairing_emits_submission_id_not_plot_id():
    p = m.Pairing("Q1", "a@x.com", "tree", "T1", "Ana", "r")
    a = m.build_link_attributes(p, "Gov")
    assert a["SunMint Submission Message ID"] == "T1"
    assert "Plot ID" not in a
    assert a["QR Code"] == "Q1" and a["Updated by"] == "Gov"


def test_plot_pairing_emits_plot_id_not_submission_id():
    p = m.Pairing("Q1", "", "plot", "P1", "Farm X", "r")
    a = m.build_link_attributes(p, "Gov")
    assert a["Plot ID"] == "P1"
    assert "SunMint Submission Message ID" not in a


# ── safety: dry-run default + execute gate ───────────────────────────────────


def test_execute_without_yes_refuses_and_fires_nothing(monkeypatch):
    """--execute requires --yes; without it we must not submit anything."""
    fired = []

    class FakeClient:
        @classmethod
        def from_env(cls, *a, **k):
            return cls()

        def submit(self, *a, **k):
            fired.append(a)
            raise AssertionError("submit must NOT be called without --yes")

    monkeypatch.setattr(m, "load_sold_unlinked_qrs", lambda gc: [_qr("Q1", "a@x.com")])
    monkeypatch.setattr(m, "load_tree_units", lambda gc: [_tree("T1")])
    monkeypatch.setattr(m, "load_plots", lambda gc: [])
    monkeypatch.setattr(m, "_gspread_client", lambda: object())

    import truesight_dao_client.edgar_client as ec

    monkeypatch.setattr(ec, "EdgarClient", FakeClient)

    rc = m.main(["--execute"])
    assert rc == 2
    assert fired == []


def test_dry_run_is_the_default_and_fires_nothing(monkeypatch, capsys):
    fired = []
    monkeypatch.setattr(m, "load_sold_unlinked_qrs", lambda gc: [_qr("Q1", "a@x.com")])
    monkeypatch.setattr(m, "load_tree_units", lambda gc: [_tree("T1")])
    monkeypatch.setattr(m, "load_plots", lambda gc: [])
    monkeypatch.setattr(m, "_gspread_client", lambda: object())

    rc = m.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert fired == []


# ── one unit per physical tree (Gary 2026-09-20: one signed RSA per tree) ──────


def _sm_row(update_id, msg_id, photo, status="NEW", linked="", farmer="Edgar"):
    """Build a SunMint Tree Planting row in the columns the loader reads."""
    row = [""] * 20
    row[m.SM_MESSAGE_ID_COL] = msg_id
    row[m.SM_PHOTO_COL] = photo
    row[m.SM_CONTRIBUTOR_COL] = farmer
    row[m.SM_STATUS_COL] = status
    row[m.SM_LINKED_QR_COL] = linked
    row[0] = update_id
    return row


def test_select_tree_units_collapses_identical_rows():
    # Same tree ingested twice (identical photo + msg id) -> one unit.
    rows = [
        _sm_row("U1", "E_001", "https://x/tree02.jpg"),
        _sm_row("U1", "E_001", "https://x/tree02.jpg"),
    ]
    units = m.select_tree_units(rows)
    assert len(units) == 1
    assert units[0].submission_message_id == "E_001"
    assert units[0].identity == "https://x/tree02.jpg"
    assert units[0].source_row == 2
    assert units[0].duplicate_rows == (3,)


def test_select_tree_units_keeps_distinct_trees_with_shared_message_id():
    # Distinct photos => distinct trees even if they share a Telegram message id.
    rows = [
        _sm_row("U1", "E_001", "https://x/tree02.jpg"),
        _sm_row("U1", "E_001", "https://x/tree03.jpg"),
    ]
    units = m.select_tree_units(rows)
    assert len(units) == 2
    assert {u.identity for u in units} == {
        "https://x/tree02.jpg",
        "https://x/tree03.jpg",
    }


def test_select_tree_units_skips_group_when_any_row_already_linked():
    # One copy already linked -> the whole tree is done; never re-offer it.
    rows = [
        _sm_row("U1", "E_001", "https://x/tree02.jpg", linked="QRX"),
        _sm_row("U1", "E_001", "https://x/tree02.jpg"),
    ]
    assert m.select_tree_units(rows) == []


def test_select_tree_units_skips_unphotographed_and_unlinked_status_only():
    rows = [
        _sm_row("U1", "E_001", ""),  # no photo -> not a Decision-0.5 target
        _sm_row("U2", "E_002", "https://x/tree03.jpg", status="LINKED"),
    ]
    assert m.select_tree_units(rows) == []


def test_compute_allocations_never_assigns_one_tree_to_two_qrs():
    # Two distinct-email QRs, one tree -> second QR gets NO tree (1:1 preserved).
    tree = _tree("E_001")
    pairs, un = m.compute_allocations(
        [_qr("Q1", "a@x.com"), _qr("Q2", "b@x.com")], [tree], []
    )
    tree_targets = [p.target_id for p in pairs if p.kind == "tree"]
    assert tree_targets == ["E_001"]  # exactly once
    assert [q.qr_code for q in un] == ["Q2"]


def test_compute_allocations_dedupes_duplicate_tree_units_defensively():
    # Same identity passed twice into the core -> still one usable unit.
    t = m.TreeUnit(submission_message_id="E_001", identity="https://x/tree02.jpg")
    dup = m.TreeUnit(submission_message_id="E_001", identity="https://x/tree02.jpg")
    pairs, un = m.compute_allocations(
        [_qr("Q1", "a@x.com"), _qr("Q2", "b@x.com")], [t, dup], []
    )
    assert len([p for p in pairs if p.kind == "tree"]) == 1
    assert [q.qr_code for q in un] == ["Q2"]
