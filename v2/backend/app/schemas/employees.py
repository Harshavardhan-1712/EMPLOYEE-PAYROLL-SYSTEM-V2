from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import CleanStr

Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]{1,32}$")]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("9999999.99"), max_digits=10, decimal_places=2)]
Hours = Annotated[Decimal, Field(ge=0, le=744, max_digits=6, decimal_places=2)]  # 744 = hours in a 31-day month
Name = Annotated[CleanStr, Field(min_length=1, max_length=120)]
Dept = Annotated[CleanStr, Field(min_length=1, max_length=80)]


class EmployeeIn(BaseModel):
    employee_code: Code
    name: Name
    department: Dept
    designation: Dept
    joining_date: date | None = None
    basic_salary: Money
    bonus: Money = Decimal("0")
    deductions: Money = Decimal("0")
    overtime_hours: Hours = Decimal("0")
    attendance_days: Annotated[int, Field(ge=0, le=31)] = 0


class EmployeePatch(BaseModel):
    """employee_code is immutable by design (it is the key payroll history refers to)."""
    model_config = {"extra": "forbid"}
    name: Name | None = None
    department: Dept | None = None
    designation: Dept | None = None
    joining_date: date | None = None
    basic_salary: Money | None = None
    bonus: Money | None = None
    deductions: Money | None = None
    overtime_hours: Hours | None = None
    attendance_days: Annotated[int, Field(ge=0, le=31)] | None = None


class EmployeeOut(BaseModel):
    id: int
    employee_code: str
    name: str
    department: str
    designation: str
    joining_date: date | None
    status: str
    basic_salary: Decimal
    bonus: Decimal
    deductions: Decimal
    overtime_hours: Decimal
    attendance_days: int
    is_sample: bool
    created_at: datetime
    updated_at: datetime
