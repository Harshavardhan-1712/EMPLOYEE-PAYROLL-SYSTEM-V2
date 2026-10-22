from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from .employees import Hours, Money

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class RunCreate(BaseModel):
    period: str

    @field_validator("period")
    @classmethod
    def _p(cls, v: str) -> str:
        if not PERIOD_RE.match(v):
            raise ValueError("period must be YYYY-MM")
        return v


class ItemPatch(BaseModel):
    """Per-period adjustments. Basic salary comes from the employee record at draft creation."""
    model_config = {"extra": "forbid"}
    bonus: Money | None = None
    deductions: Money | None = None
    overtime_hours: Hours | None = None
    attendance_days: Annotated[int, Field(ge=0, le=31)] | None = None


class FinalizeIn(BaseModel):
    acknowledge_errors: bool = False
    note: str | None = Field(default=None, max_length=500)


class ReverseIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class FlagOut(BaseModel):
    code: str
    severity: str
    message: str


class ItemOut(BaseModel):
    id: int
    employee_id: int
    employee_code: str
    employee_name: str
    department: str
    designation: str
    basic_salary: Decimal
    bonus: Decimal
    overtime_hours: Decimal
    overtime_rate: Decimal
    overtime_pay: Decimal
    gross_salary: Decimal
    deductions: Decimal
    net_salary: Decimal
    attendance_days: int
    flags: list[FlagOut]


class RunOut(BaseModel):
    id: int
    period: str
    status: str
    is_sample: bool
    overtime_rate: Decimal
    employee_count: int
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    error_flag_items: int
    warning_flag_items: int
    created_at: datetime
    reviewed_at: datetime | None
    finalized_at: datetime | None
    reversed_at: datetime | None
    reversal_reason: str | None
    totals_source: str  # "snapshot" (finalized) | "live" (draft/reviewed, may still change)


class RunDetail(RunOut):
    items: list[ItemOut]


class SettingsOut(BaseModel):
    overtime_rate: Decimal
    high_overtime_hours: Decimal
    unusual_salary_change_pct: Decimal
    require_separate_finalizer: bool


class SettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}
    overtime_rate: Money | None = None
    high_overtime_hours: Annotated[Decimal, Field(ge=0, le=744, decimal_places=2)] | None = None
    unusual_salary_change_pct: Annotated[Decimal, Field(ge=0, le=1000, decimal_places=2)] | None = None
    require_separate_finalizer: bool | None = None
