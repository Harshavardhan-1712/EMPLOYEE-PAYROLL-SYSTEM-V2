"""Explainable review flags. These are indicators for a human reviewer, not findings of error or fraud.

severity "error"   -> blocks finalization unless the approver explicitly acknowledges (and that is audited)
severity "warning" -> informational
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from decimal import Decimal

from .payroll_rules import paise_to_rupees
from .settings_store import PayrollSettings


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message}


def days_in_period(period: str) -> int:
    y, m = int(period[:4]), int(period[5:7])
    return calendar.monthrange(y, m)[1]


def evaluate(*, period: str, net_paise: int, overtime_hours: Decimal, attendance_days: int, basic_paise: int,
             joining_date, previous_basic_paise: int | None, cfg: PayrollSettings) -> list[Flag]:
    out: list[Flag] = []
    if net_paise < 0:
        out.append(Flag("negative_net", "error",
                        f"Net pay is negative ({paise_to_rupees(net_paise)}): deductions exceed gross pay."))
    dim = days_in_period(period)
    if attendance_days > dim:
        out.append(Flag("attendance_exceeds_period", "error",
                        f"Attendance of {attendance_days} days exceeds the {dim} days in {period}."))
    if overtime_hours > cfg.high_overtime_hours:
        out.append(Flag("high_overtime", "warning",
                        f"Overtime of {overtime_hours} h exceeds the review threshold of {cfg.high_overtime_hours} h."))
    if joining_date is None:
        out.append(Flag("missing_joining_date", "warning", "Joining date is not recorded."))
    if previous_basic_paise and previous_basic_paise > 0 and basic_paise != previous_basic_paise:
        pct = (Decimal(basic_paise - previous_basic_paise) / Decimal(previous_basic_paise)) * 100
        if abs(pct) > cfg.unusual_salary_change_pct:
            out.append(Flag("unusual_salary_change", "warning",
                            f"Basic salary changed {pct:+.1f}% versus the last finalized run "
                            f"(review threshold {cfg.unusual_salary_change_pct}%)."))
    return out
