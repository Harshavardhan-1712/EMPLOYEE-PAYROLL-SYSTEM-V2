"""V2 schema. Money is stored as integer paise; see docs/schema.md."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DDL, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
    event, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_sample: Mapped[bool] = mapped_column(default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # bumped on password change/reset: old sessions stop working
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("role IN ('viewer','hr_editor','payroll_approver','admin')", name="ck_user_role"),
    )


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(80))
    designation: Mapped[str] = mapped_column(String(80))
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="active")
    basic_salary_paise: Mapped[int] = mapped_column(Integer)
    bonus_paise: Mapped[int] = mapped_column(Integer, default=0)
    deductions_paise: Mapped[int] = mapped_column(Integer, default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))
    attendance_days: Mapped[int] = mapped_column(Integer, default=0)
    is_sample: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="ck_emp_status"),
        CheckConstraint("basic_salary_paise >= 0 AND bonus_paise >= 0 AND deductions_paise >= 0", name="ck_emp_money_nonneg"),
        CheckConstraint("overtime_hours >= 0 AND attendance_days >= 0", name="ck_emp_counts_nonneg"),
        Index("ix_emp_dept_status", "department", "status"),
    )


class SalaryHistory(Base):
    """Append-only log of basic-salary changes (feeds 'unusual salary change' flags)."""
    __tablename__ = "employee_salary_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    old_basic_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_basic_paise: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "payroll_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    status: Mapped[str] = mapped_column(String(10), default="draft")
    overtime_rate_paise: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_sample: Mapped[bool] = mapped_column(default=False)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_gross_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_deductions_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_net_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    items: Mapped[list["PayrollRunItem"]] = relationship(back_populates="run")
    __table_args__ = (
        CheckConstraint("status IN ('draft','reviewed','finalized','reversed')", name="ck_run_status"),
        CheckConstraint("overtime_rate_paise >= 0", name="ck_run_rate"),
        CheckConstraint("period GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'", name="ck_run_period_fmt"),
        # one live run per period; a reversed run frees the period for a corrected run
        Index("uq_run_period_live", "period", unique=True, sqlite_where=text("status != 'reversed'")),
    )


class PayrollRunItem(Base):
    """Employee-level snapshot. Identity fields are copied so later edits never rewrite history."""
    __tablename__ = "payroll_run_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"), index=True)
    employee_code: Mapped[str] = mapped_column(String(32))
    employee_name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(80))
    designation: Mapped[str] = mapped_column(String(80))
    basic_paise: Mapped[int] = mapped_column(Integer)
    bonus_paise: Mapped[int] = mapped_column(Integer)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    overtime_rate_paise: Mapped[int] = mapped_column(Integer)
    overtime_pay_paise: Mapped[int] = mapped_column(Integer)
    gross_paise: Mapped[int] = mapped_column(Integer)
    deductions_paise: Mapped[int] = mapped_column(Integer)
    net_paise: Mapped[int] = mapped_column(Integer)  # may be negative: flagged, never silently clamped
    attendance_days: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of {code, message}
    run: Mapped[PayrollRun] = relationship(back_populates="items")
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_item_run_emp"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")  # JSON; never passwords/tokens


# --- Immutability of finalized payroll, enforced in the database itself -------------------------
_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS trg_items_no_update BEFORE UPDATE ON payroll_run_items
       WHEN (SELECT status FROM payroll_runs WHERE id = OLD.run_id) IN ('finalized','reversed')
       BEGIN SELECT RAISE(ABORT, 'finalized payroll items are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_items_no_delete BEFORE DELETE ON payroll_run_items
       WHEN (SELECT status FROM payroll_runs WHERE id = OLD.run_id) IN ('finalized','reversed')
       BEGIN SELECT RAISE(ABORT, 'finalized payroll items are immutable'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_items_no_insert BEFORE INSERT ON payroll_run_items
       WHEN (SELECT status FROM payroll_runs WHERE id = NEW.run_id) IN ('finalized','reversed')
       BEGIN SELECT RAISE(ABORT, 'cannot add items to a finalized payroll run'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_runs_no_delete BEFORE DELETE ON payroll_runs
       WHEN OLD.status IN ('finalized','reversed')
       BEGIN SELECT RAISE(ABORT, 'finalized payroll runs cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_runs_frozen BEFORE UPDATE ON payroll_runs
       WHEN OLD.status = 'reversed'
         OR (OLD.status = 'finalized' AND (
              NEW.status NOT IN ('finalized','reversed')
           OR NEW.period IS NOT OLD.period
           OR NEW.overtime_rate_paise IS NOT OLD.overtime_rate_paise
           OR NEW.employee_count IS NOT OLD.employee_count
           OR NEW.total_gross_paise IS NOT OLD.total_gross_paise
           OR NEW.total_deductions_paise IS NOT OLD.total_deductions_paise
           OR NEW.total_net_paise IS NOT OLD.total_net_paise
           OR NEW.finalized_by IS NOT OLD.finalized_by
           OR NEW.finalized_at IS NOT OLD.finalized_at))
       BEGIN SELECT RAISE(ABORT, 'finalized payroll runs are immutable; reverse explicitly instead'); END""",
]
for _sql in _TRIGGERS:
    event.listen(Base.metadata, "after_create", DDL(_sql))
