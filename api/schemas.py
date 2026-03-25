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
    min_operating_margin: float | None = None
    min_roi: float | None = None
    min_revenue_yoy: float | None = None
    min_eps: float | None = None
    min_gross_margin_yoy_delta: float | None = None
    max_share_capital: float | None = None
    industry: str | None = None


class ScreenMetricOut(BaseModel):
    gross_margin: float | None = None
    operating_margin: float | None = None
    roi: float | None = None
    eps: float | None = None
    revenue_yoy: float | None = None
    share_capital_billion: float | None = None
    gross_margin_yoy_delta: float | None = None


class ScreenItemOut(BaseModel):
    ticker: str
    name: str
    industry: str | None = None
    latest_month: date | None = None
    latest_quarter: str | None = None
    metrics: ScreenMetricOut


class ScreenResponseOut(BaseModel):
    count: int
    total: int
    limit: int
    offset: int
    items: list[ScreenItemOut]


class ScreenMetadataOut(BaseModel):
    industries: list[str]
    default_filters: ScreeningRequest
    data_as_of: dict[str, str | None]
