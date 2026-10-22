from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PayslipOut(BaseModel):
    run_id: int
    period: str
    period_label: str
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
    finalized_at: datetime | None
    company_name: str


class PayslipRow(BaseModel):
    run_id: int
    employee_id: int
    period: str
    employee_code: str
    employee_name: str
    department: str
    gross_salary: Decimal
    deductions: Decimal
    net_salary: Decimal
