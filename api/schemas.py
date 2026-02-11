from __future__ import annotations

from datetime import date
from pydantic import BaseModel


class MonthlyRevenueOut(BaseModel):
    ticker: str
    period: date
    month_revenue: float | None = None
    month_mom_pct: float | None = None
    month_prev_year_revenue: float | None = None
    month_yoy_pct: float | None = None
    cum_revenue: float | None = None
    cum_prev_year_revenue: float | None = None
    cum_yoy_pct: float | None = None

    class Config:
        from_attributes = True


class ScreeningRequest(BaseModel):
    min_gross_margin: float | None = None
    min_roi: float | None = None
    min_revenue_yoy: float | None = None
    max_share_capital: float | None = None
    industry: str | None = None
