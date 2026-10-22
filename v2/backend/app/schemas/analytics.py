from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class RunBrief(BaseModel):
    id: int
    period: str
    status: str
    employee_count: int
    total_net: Decimal
    is_sample: bool
    created_at: datetime


class DeptRow(BaseModel):
    department: str
    employees: int
    gross: Decimal
    deductions: Decimal
    net: Decimal


class TrendPoint(BaseModel):
    period: str
    employees: int
    gross: Decimal
    deductions: Decimal
    net: Decimal
    bonus: Decimal
    overtime_pay: Decimal
    overtime_hours: Decimal


class Comparison(BaseModel):
    period: str                      # the most recent finalized period before the selected one (may not be the adjacent month)
    employee_count: int
    total_net: Decimal
    net_change: Decimal
    net_change_pct: Decimal | None   # null when the earlier net is zero or negative
    adjacent_month: bool


class AttentionItem(BaseModel):
    kind: str                        # open_run | missing_joining_date
    message: str
    severity: str                    # info | warning | error
    link: str


class DashboardSummary(BaseModel):
    active_employees: int
    inactive_employees: int
    sample_employees: int
    available_periods: list[str]
    selected_period: str | None
    has_history: bool
    run_id: int | None
    employee_count: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    average_net: Decimal | None
    total_bonus: Decimal
    total_overtime_pay: Decimal
    comparison: Comparison | None
    departments: list[DeptRow]
    trend: list[TrendPoint]
    trend_min_periods: int
    recent_runs: list[RunBrief]
    attention: list[AttentionItem]
    includes_sample_data: bool


class Bucket(BaseModel):
    start: Decimal
    end: Decimal
    count: int


class Extreme(BaseModel):
    employee_code: str
    employee_name: str
    period: str
    net: Decimal


class OvertimeRow(BaseModel):
    employee_code: str
    employee_name: str
    period: str
    hours: Decimal
    pay: Decimal


class OvertimeDept(BaseModel):
    department: str
    hours: Decimal
    pay: Decimal


class ChangeRow(BaseModel):
    period: str
    prior_period: str
    employee_count: int
    employee_count_change: int
    net: Decimal
    net_change: Decimal
    net_change_pct: Decimal | None


class QualityFlag(BaseModel):
    run_id: int
    period: str
    employee_code: str
    employee_name: str
    code: str
    severity: str
    message: str


class QualityCheck(BaseModel):
    code: str
    count: int
    message: str


class AnalyticsSummary(BaseModel):
    from_period: str | None
    to_period: str | None
    department: str | None
    available_periods: list[str]
    departments: list[str]
    periods_in_scope: int
    record_count: int
    includes_sample_data: bool
    totals: dict[str, Decimal]
    average_net: Decimal | None
    highest_net: Extreme | None
    lowest_net: Extreme | None
    distribution: list[Bucket]
    by_department: list[DeptRow]
    trend: list[TrendPoint]
    changes: list[ChangeRow]
    attendance: dict[str, Decimal | int | None]
    overtime_records: int
    overtime_avg_hours: Decimal | None
    overtime_top: list[OvertimeRow]
    overtime_by_department: list[OvertimeDept]
    flag_counts: dict[str, int]
    flagged_records: list[QualityFlag]
    employee_checks: list[QualityCheck]
    thresholds: dict[str, Decimal]
