"""Parity: V2 rules must equal V1 payroll.py. V1 is loaded READ-ONLY from a temp copy so importing it
cannot create files or touch employee_data.db inside the real V1 tree."""
from __future__ import annotations

import importlib.util
import random
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import V1_ROOT
from app.services.payroll_rules import DEFAULT_OVERTIME_RATE_PAISE, compute_payroll, to_paise

V1_FILES = ["payroll.py", "database.py"]


@pytest.fixture(scope="module")
def v1(tmp_path_factory):
    if not (V1_ROOT / "payroll.py").exists():
        pytest.skip("V1 payroll.py not found next to v2/")
    tmp = tmp_path_factory.mktemp("v1copy")
    for f in V1_FILES:
        shutil.copy2(V1_ROOT / f, tmp / f)
    sys.path.insert(0, str(tmp))
    try:
        spec = importlib.util.spec_from_file_location("v1_payroll", tmp / "payroll.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path.remove(str(tmp))
        for m in ("database", "v1_payroll"):
            sys.modules.pop(m, None)


def test_v1_rate_constant_matches(v1):
    assert v1.OVERTIME_RATE == 200
    assert to_paise(v1.OVERTIME_RATE) == DEFAULT_OVERTIME_RATE_PAISE


def test_formula_parity_random(v1):
    """V1's compute_payroll_for_employee (pure, takes a dict) vs V2 compute_payroll, 500 random employees."""
    rng = random.Random(42)
    for i in range(500):
        emp = {
            "emp_id": i, "name": "X", "department": "D", "designation": "T",
            "basic_salary": round(rng.uniform(0, 500_000), 2), "bonus": round(rng.uniform(0, 50_000), 2),
            "deductions": round(rng.uniform(0, 600_000), 2),   # includes negative-net cases
            "attendance": rng.randint(0, 31), "overtime": rng.randint(0, 120),
        }
        v1r = v1.compute_payroll_for_employee(emp)
        r = compute_payroll(basic_paise=to_paise(emp["basic_salary"]), bonus_paise=to_paise(emp["bonus"]),
                            overtime_hours=emp["overtime"], deductions_paise=to_paise(emp["deductions"]))
        assert Decimal(r.overtime_pay_paise) / 100 == Decimal(str(v1r["overtime_pay"]))
        assert abs(float(Decimal(r.gross_paise) / 100) - v1r["gross_salary"]) < 0.005
        assert abs(float(Decimal(r.net_paise) / 100) - v1r["net_salary"]) < 0.005
