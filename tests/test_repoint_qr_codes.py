"""Tests for the QR repoint primitive.

The interesting behaviour is not the write -- it is the *refusals*. Each test
below pins one way this could corrupt the ledger.
"""

from __future__ import annotations

from truesight_dao_client.modules.repoint_qr_codes import (
    COL_MANAGER,
    COL_SKU,
    QrRow,
    _letter,
    _near_miss,
    plan_repoint,
)

KIRSTEN = "Kirsten Ritschel"
MATHEUS = "Matheus Reis"
SHORT_SKU = "Ceremonial Cacao Kraft Pouch - 20250219006"
AWB_SKU = (
    "Ceremonial Cacao Kraft Pouch - 20250219006 | Cacao Mass | 200 grams | "
    "Paulo 2024 | Santos 018-2025 016-2025 || Ilheus - AGL8 + 047-3175-3223 - San Francisco"
)


def _row(
    row=780,
    code="2024PAULO_20251018",
    currency=SHORT_SKU,
    manager=MATHEUS,
    status="MINTED",
):
    return QrRow(
        row=row, qr_code=code, currency=currency, manager=manager, status=status
    )


class TestColumnLetters:
    def test_manager_is_u(self):
        assert _letter(COL_MANAGER) == "U"

    def test_currency_is_i(self):
        assert _letter(COL_SKU) == "I"

    def test_two_letter_column(self):
        assert _letter(27) == "AA"


class TestValidation:
    def test_unknown_manager_is_refused(self):
        """A near-miss name would spawn a duplicate contributor row."""
        plan = plan_repoint(
            [_row()],
            new_manager="Kirsten Ritshel",  # typo
            known_managers={KIRSTEN, MATHEUS},
        )
        assert not plan.ok
        assert any("duplicate contributor" in e for e in plan.errors)
        assert plan.changes == []

    def test_typo_suggestion_offered(self):
        plan = plan_repoint(
            [_row()],
            new_manager="Kirsten Ritshel",
            known_managers={KIRSTEN},
        )
        assert KIRSTEN in plan.errors[0]

    def test_unknown_currency_is_refused(self):
        """A hand-typed 130-char SKU is exactly where a typo hides."""
        plan = plan_repoint(
            [_row()],
            new_currency=AWB_SKU + "x",
            known_currencies={SHORT_SKU, AWB_SKU},
        )
        assert not plan.ok
        assert any("Currencies" in e for e in plan.errors)

    def test_whitespace_in_target_is_refused(self):
        plan = plan_repoint([_row()], new_manager=KIRSTEN + " ")
        assert not plan.ok
        assert any("whitespace" in e for e in plan.errors)

    def test_empty_target_is_refused(self):
        plan = plan_repoint([_row()], new_manager="   ")
        assert not plan.ok

    def test_nothing_to_change_is_an_error(self):
        plan = plan_repoint([_row()])
        assert not plan.ok
        assert any("Nothing to change" in e for e in plan.errors)

    def test_no_rows_is_an_error(self):
        assert not plan_repoint([], new_manager=KIRSTEN).ok


class TestSoldRowGuard:
    def test_sold_row_is_refused(self):
        plan = plan_repoint([_row(status="SOLD")], new_manager=KIRSTEN)
        assert not plan.ok
        assert any("settled row" in e for e in plan.errors)

    def test_sold_row_allowed_with_override(self):
        plan = plan_repoint(
            [_row(status="SOLD")],
            new_manager=KIRSTEN,
            allow_sold=True,
        )
        assert plan.ok
        assert len(plan.changes) == 1

    def test_unknown_status_is_allowed(self):
        plan = plan_repoint([_row(status="MINTED")], new_manager=KIRSTEN)
        assert plan.ok


class TestChangePlanning:
    def test_repoints_both_columns(self):
        plan = plan_repoint(
            [_row()],
            new_manager=KIRSTEN,
            new_currency=AWB_SKU,
            known_managers={KIRSTEN},
            known_currencies={AWB_SKU},
        )
        assert plan.ok
        fields = {c.field_name for c in plan.changes}
        assert fields == {"Manager Name", "Currency"}

    def test_only_changed_cells_written(self):
        """Rows already holding the target must not be rewritten."""
        plan = plan_repoint(
            [_row(manager=KIRSTEN, currency=AWB_SKU)],
            new_manager=KIRSTEN,
            new_currency=AWB_SKU,
            known_managers={KIRSTEN},
            known_currencies={AWB_SKU},
        )
        assert plan.ok
        assert plan.changes == []
        assert plan.unchanged == 1

    def test_partial_match_writes_only_the_diff(self):
        plan = plan_repoint(
            [_row(manager=KIRSTEN, currency=SHORT_SKU)],
            new_manager=KIRSTEN,
            new_currency=AWB_SKU,
            known_managers={KIRSTEN},
            known_currencies={AWB_SKU},
        )
        assert [c.field_name for c in plan.changes] == ["Currency"]

    def test_old_value_is_captured_for_reversal(self):
        plan = plan_repoint([_row()], new_currency=AWB_SKU, known_currencies={AWB_SKU})
        change = next(c for c in plan.changes if c.field_name == "Currency")
        assert change.old == SHORT_SKU
        assert change.new == AWB_SKU

    def test_touched_rows_deduped(self):
        plan = plan_repoint([_row()], new_manager=KIRSTEN, new_currency=AWB_SKU)
        assert plan.touched_rows == [780]

    def test_duplicate_qr_codes_warned(self):
        plan = plan_repoint(
            [_row(row=10, code="DUP"), _row(row=11, code="DUP")],
            new_manager=KIRSTEN,
        )
        assert any("Duplicate QR codes" in w for w in plan.warnings)

    def test_errors_block_all_writes(self):
        """One bad row must abort the whole batch -- no partial repoint."""
        plan = plan_repoint(
            [
                _row(row=10, code="OK_MINTED"),
                _row(row=11, code="OK_SOLD", status="SOLD"),
            ],
            new_manager=KIRSTEN,
        )
        assert not plan.ok
        assert plan.changes == []


class TestNearMiss:
    def test_case_insensitive_exact(self):
        assert _near_miss("kirsten ritschel", {KIRSTEN}) == KIRSTEN

    def test_prefix_match(self):
        assert _near_miss("Kirsten", {KIRSTEN, MATHEUS}) == KIRSTEN

    def test_no_match_returns_none(self):
        assert _near_miss("zzz", {KIRSTEN}) is None
