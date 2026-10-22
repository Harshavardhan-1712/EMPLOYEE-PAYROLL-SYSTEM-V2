from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import Setting

# Starting defaults. overtime rate = V1's Rs 200. The two review thresholds are developer-chosen starting points
# for *review flags only* -- not statutory or policy values. Admins can change all three.
DEFAULTS = {"overtime_rate_paise": "20000", "high_overtime_hours": "40", "unusual_salary_change_pct": "25",
            "require_separate_finalizer": "false"}


@dataclass(frozen=True)
class PayrollSettings:
    overtime_rate_paise: int
    high_overtime_hours: Decimal
    unusual_salary_change_pct: Decimal
    require_separate_finalizer: bool = False


def load(db: Session) -> PayrollSettings:
    def get(k: str) -> str:
        row = db.get(Setting, k)
        return row.value if row else DEFAULTS[k]
    return PayrollSettings(int(get("overtime_rate_paise")), Decimal(get("high_overtime_hours")),
                           Decimal(get("unusual_salary_change_pct")), get("require_separate_finalizer") == "true")
