from truesight_dao_client.modules.report_contribution import _authoritative_tdg


def test_wrong_tdg_is_overridden(capsys):
    attrs = [("Type", "Time (Minutes)"), ("Amount", "45"),
             ("Contributor(s)", "Gary Teh"), ("TDG Issued", "750")]
    out = dict(_authoritative_tdg(attrs))
    assert out["TDG Issued"] == "75.00"
    assert "IGNORED" in capsys.readouterr().err


def test_tdg_inserted_when_absent():
    attrs = [("Type", "Time (Minutes)"), ("Amount", "60"), ("Contributor(s)", "Gary Teh")]
    out = dict(_authoritative_tdg(attrs))
    assert out["TDG Issued"] == "100.00"


def test_matching_tdg_no_warning(capsys):
    attrs = [("Type", "Time (Minutes)"), ("Amount", "45"),
             ("Contributor(s)", "Gary Teh"), ("TDG Issued", "75.00")]
    _authoritative_tdg(attrs)
    assert "IGNORED" not in capsys.readouterr().err


def test_no_type_or_amount_returns_as_is():
    attrs = [("Contributor(s)", "Gary Teh")]
    out = _authoritative_tdg(attrs)
    assert out == attrs


def test_usd_tdg():
    attrs = [("Type", "USD"), ("Amount", "27.70"), ("Contributor(s)", "Gary Teh")]
    out = dict(_authoritative_tdg(attrs))
    assert out["TDG Issued"] == "27.70"
