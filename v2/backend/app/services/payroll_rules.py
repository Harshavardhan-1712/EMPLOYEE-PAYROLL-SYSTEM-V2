"""Single source of payroll rules in V2 (mirrors V1 payroll.py exactly).

    overtime_pay = overtime_hours x overtime_rate
    gross        = basic + bonus + overtime_pay
    net          = gross - deductions

No statutory deductions (PF/ESI/TDS/tax) are implemented: their rules have not been defined.
All money is integer paise. Rounding (half-up) happens in exactly one place: overtime pay.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISE = Decimal(100)
DEFAULT_OVERTIME_RATE_PAISE = 200 * 100  # V1 constant: Rs 200 / hour


class PayrollInputError(ValueError):
    """Invalid payroll input (negative, non-numeric, ...)."""


def to_paise(value: int | float | str | Decimal, field: str = "amount") -> int:
    """Rupees -> integer paise. Goes via str() so 0.1 does not become 0.1000000000000000055."""
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise PayrollInputError(f"{field} is not a valid number") from exc
    if not d.is_finite():
        raise PayrollInputError(f"{field} is not a valid number")
    return int((d * PAISE).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> Decimal:
    return (Decimal(paise) / PAISE).quantize(Decimal("0.01"))


def _hours(value: int | float | str | Decimal) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise PayrollInputError("overtime_hours is not a valid number") from exc
    if not d.is_finite():
        raise PayrollInputError("overtime_hours is not a valid number")
    return d


@dataclass(frozen=True)
class PayrollResult:
    basic_paise: int
    bonus_paise: int
    overtime_hours: Decimal
    overtime_rate_paise: int
    overtime_pay_paise: int
    gross_paise: int
    deductions_paise: int
    net_paise: int

    @property
    def negative_net(self) -> bool:
        return self.net_paise < 0


def calc_overtime_pay(overtime_hours: Decimal | int | float | str, rate_paise: int) -> int:
    hours = _hours(overtime_hours)
    if hours < 0:
        raise PayrollInputError("overtime_hours cannot be negative")
    if rate_paise < 0:
        raise PayrollInputError("overtime rate cannot be negative")
    return int((hours * rate_paise).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def compute_payroll(
    *, basic_paise: int, bonus_paise: int, overtime_hours: Decimal | int | float | str,
    deductions_paise: int, overtime_rate_paise: int = DEFAULT_OVERTIME_RATE_PAISE,
) -> PayrollResult:
    for name, v in (("basic salary", basic_paise), ("bonus", bonus_paise), ("deductions", deductions_paise)):
        if not isinstance(v, int) or isinstance(v, bool):
            raise PayrollInputError(f"{name} must be integer paise")
        if v < 0:
            raise PayrollInputError(f"{name} cannot be negative")
    ot_pay = calc_overtime_pay(overtime_hours, overtime_rate_paise)
    gross = basic_paise + bonus_paise + ot_pay
    return PayrollResult(
        basic_paise=basic_paise, bonus_paise=bonus_paise, overtime_hours=_hours(overtime_hours),
        overtime_rate_paise=overtime_rate_paise, overtime_pay_paise=ot_pay, gross_paise=gross,
        deductions_paise=deductions_paise, net_paise=gross - deductions_paise,
    )
