import pytest
from truesight_dao_client.rubric import tdg_for, format_tdg, amount_and_tdg_from_time, parse_amount


def test_time_minutes():
    assert tdg_for("Time (Minutes)", 60) == 100.0
    assert tdg_for("Time (Minutes)", 45) == 75.0
    assert tdg_for("Time (Minutes)", 30) == 50.0
    assert format_tdg(tdg_for("Time (Minutes)", 35)) == "58.33"


def test_time_internal_type():
    assert tdg_for("Time", 60) == 100.0


def test_usd_and_usdt_one_to_one():
    assert tdg_for("USD", 27.70) == 27.70
    assert tdg_for("USDT received", 100) == 100.0
    assert tdg_for("USDT sent", 50) == 50.0


def test_amount_and_tdg_from_time():
    assert amount_and_tdg_from_time(0, 45) == ("45", "75.00")
    assert amount_and_tdg_from_time(1, 30) == ("90", "150.00")


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        tdg_for("Software", 10)


def test_amount_parsing():
    assert parse_amount("$1,234.50") == 1234.50
    with pytest.raises(ValueError):
        parse_amount("abc")


def test_amount_none_raises():
    with pytest.raises(ValueError):
        parse_amount(None)


def test_empty_type_raises():
    with pytest.raises(ValueError):
        tdg_for("", 100)
