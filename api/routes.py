from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import MonthlyRevenue
from .schemas import MonthlyRevenueOut

router = APIRouter()


@router.get("/monthly-revenue/{ticker}", response_model=list[MonthlyRevenueOut])
def monthly_revenue(ticker: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(MonthlyRevenue)
        .where(MonthlyRevenue.ticker == ticker)
        .order_by(MonthlyRevenue.period.desc())
    ).scalars().all()
    return rows
