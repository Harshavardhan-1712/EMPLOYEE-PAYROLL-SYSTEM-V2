from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas.analytics import AnalyticsSummary, DashboardSummary
from ..security.deps import require
from ..services import analytics as svc

router = APIRouter(tags=["analytics"])
PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(period: str | None = Query(None, pattern=PERIOD), db: Session = Depends(get_db), _: User = Depends(require("analytics:read"))):
    return svc.dashboard(db, period)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(period_from: str | None = Query(None, alias="from", pattern=PERIOD), period_to: str | None = Query(None, alias="to", pattern=PERIOD),
                      department: str | None = Query(None, max_length=80), db: Session = Depends(get_db), _: User = Depends(require("analytics:read"))):
    return svc.analytics(db, period_from, period_to, department)
