from decimal import Decimal

import pytest

from app.services.payroll_rules import (
    DEFAULT_OVERTIME_RATE_PAISE, PayrollInputError, calc_overtime_pay, compute_payroll, paise_to_rupees, to_paise,
)


def calc(**kw):
    base = dict(basic_paise=5_000_000, bonus_paise=0, overtime_hours=0, deductions_paise=0)
    base.update(kw)
    return compute_payroll(**base)


def test_default_rate_is_v1_rs200():
    assert DEFAULT_OVERTIME_RATE_PAISE == 20_000


def test_zero_overtime():
    r = calc()
    assert (r.overtime_pay_paise, r.gross_paise, r.net_paise) == (0, 5_000_000, 5_000_000)


def test_full_formula():
    r = calc(basic_paise=50_000_00, bonus_paise=5_000_00, overtime_hours=10, deductions_paise=2_500_00)
    assert r.overtime_pay_paise == 2_000_00              # 10 h x Rs200
    assert r.gross_paise == 57_000_00                     # 50000 + 5000 + 2000
    assert r.net_paise == 54_500_00


def test_configurable_rate():
    assert calc(overtime_hours=10, overtime_rate_paise=25_000).overtime_pay_paise == 250_000


def test_fractional_hours_round_half_up_once():
    assert calc_overtime_pay(Decimal("0.5"), 101) == 51   # 50.5 -> 51
    assert calc_overtime_pay("2.25", 20_000) == 45_000


def test_negative_net_is_returned_not_clamped():
    r = calc(basic_paise=1_000_00, deductions_paise=3_000_00)
    assert r.net_paise == -2_000_00 and r.negative_net


@pytest.mark.parametrize("kw", [
    dict(basic_paise=-1), dict(bonus_paise=-1), dict(deductions_paise=-1), dict(overtime_hours=-1),
    dict(overtime_hours="abc"), dict(overtime_hours="NaN"), dict(overtime_hours="Infinity"),
    dict(basic_paise=1.5), dict(basic_paise=True), dict(overtime_rate_paise=-5),
])
def test_invalid_inputs_rejected(kw):
    with pytest.raises(PayrollInputError):
        calc(**kw)


def test_to_paise_avoids_float_error():
    assert to_paise(0.1) == 10 and to_paise("19999.99") == 1_999_999 and to_paise(1.005) == 101
    assert paise_to_rupees(1_999_999) == Decimal("19999.99")


@pytest.mark.parametrize("bad", ["x", "", None, "NaN", "inf"])
def test_to_paise_rejects_garbage(bad):
    with pytest.raises(PayrollInputError):
        to_paise(bad)
