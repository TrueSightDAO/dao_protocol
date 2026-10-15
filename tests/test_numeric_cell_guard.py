"""Appended ledger rows must store numbers as numbers.

A derived `sum(col)` view silently drops text-typed cells; a signed row whose quantity
lands as text vanishes from the aggregate (2026-10-15 Unit D incident). `base.append_row`
now coerces numeric strings, independent of the caller's valueInputOption.
"""

from __future__ import annotations

from truesight_dao_client.server.sheets import base


def test_coerce_numeric_ints_and_floats():
    assert base.coerce_numeric("2") == 2
    assert base.coerce_numeric("2.00000000") == 2.0
    assert base.coerce_numeric("-2") == -2
    assert base.coerce_numeric("+3") == 3
    assert base.coerce_numeric("1e3") == 1000.0
    assert base.coerce_numeric(".5") == 0.5


def test_coerce_numeric_leaves_non_numeric_untouched():
    assert base.coerce_numeric("Matheus Reis") == "Matheus Reis"
    assert base.coerce_numeric("") == ""
    assert base.coerce_numeric("12abc") == "12abc"
    assert base.coerce_numeric(5) == 5  # already numeric


def test_coerce_row_numeric_maps_each_cell():
    row = ["Matheus Reis", "2.00000000", "Foam container box", "-3"]
    assert base.coerce_row_numeric(row) == ["Matheus Reis", 2.0, "Foam container box", -3]


def test_append_row_coerces_before_sending(monkeypatch):
    sent = {}

    class _Vals:
        def append(self, **kw):
            sent.update(kw)
            return self

        def execute(self):
            return {}

    class _Sheets:
        def values(self):
            return _Vals()

    class _Svc:
        def spreadsheets(self):
            return _Sheets()

    monkeypatch.setattr(base, "sheets_service", lambda key_path=None: _Svc())
    base.append_row("sid", "Sheet!A:D", ["Matheus Reis", "2.00000000", "item", "-3"])
    assert sent["body"]["values"] == [["Matheus Reis", 2.0, "item", -3]]
