from __future__ import annotations

from datetime import date
from typing import Literal

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
    min_roe: float | None = None
    min_roa: float | None = None
    min_book_value_per_share: float | None = None
    min_cash_dividend: float | None = None
    market: str | None = None
    share_capital_min: float | None = None
    share_capital_max: float | None = None
    market_cap_min: float | None = None
    market_cap_max: float | None = None
    upcoming_ex_dividend_within_days: int | None = None
    max_share_capital: float | None = None
    industry: str | None = None
    period_mode: Literal["latest_available", "fixed_period"] = "latest_available"
    target_fiscal_year: int | None = None
    target_fiscal_quarter: int | None = None
    stale_policy: Literal["exclude_stale", "include_stale_with_flag"] = "exclude_stale"


class ScreenMetricOut(BaseModel):
    gross_margin: float | None = None
    operating_margin: float | None = None
    roi: float | None = None
    eps: float | None = None
    revenue_yoy: float | None = None
    share_capital_billion: float | None = None
    market_cap_million_twd: float | None = None
    gross_margin_yoy_delta: float | None = None
    roe: float | None = None
    roa: float | None = None
    book_value_per_share: float | None = None
    cash_dividend: float | None = None
    upcoming_ex_dividend_date: date | None = None
    gross_margin_period: str | None = None
    roe_period: str | None = None
    eps_period: str | None = None


class ScreenItemOut(BaseModel):
    ticker: str
    name: str
    market: str | None = None
    industry: str | None = None
    group_name: str | None = None
    latest_month: date | None = None
    latest_quarter: str | None = None
    resolved_period: str | None = None
    is_stale: bool = False
    metrics: ScreenMetricOut


class ScreenResponseOut(BaseModel):
    count: int
    total: int
    limit: int
    offset: int
    items: list[ScreenItemOut]


class ScreenMetadataOut(BaseModel):
    industries: list[str]
    markets: list[str]
    default_filters: ScreeningRequest
    data_as_of: dict[str, str | None]


class CompanyProfileOut(BaseModel):
    ticker: str
    company_name: str
    english_short_name: str | None = None
    market: str | None = None
    industry: str | None = None
    group_name: str | None = None
    chairman: str | None = None
    general_manager: str | None = None
    spokesperson: str | None = None
    acting_spokesperson: str | None = None
    website: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    address: str | None = None
    established_date: date | None = None
    listed_date: date | None = None
    share_capital: float | None = None
    issued_common_shares: int | None = None
    market_cap_million_twd: float | None = None
    director_supervisor_holding_pct: float | None = None
    stock_transfer_agent: str | None = None
    auditor: str | None = None
    business_summary: str | None = None
    data_date: date | None = None


class CompanyDividendSummaryOut(BaseModel):
    ticker: str
    dividend_year: int | None = None
    cash_dividend: float | None = None
    earnings_stock_dividend: float | None = None
    capital_reserve_stock_dividend: float | None = None
    stock_dividend: float | None = None
    is_advance_notice: bool
    data_date: date | None = None


class CompanyFinancialHighlightEpsOut(BaseModel):
    series_type: str
    period_label: str
    fiscal_year: int
    fiscal_quarter: int | None = None
    eps: float | None = None
    display_order: int


class CompanyFinancialHighlightsOut(BaseModel):
    ticker: str
    fiscal_year: int
    fiscal_quarter: int
    gross_margin: float | None = None
    operating_margin: float | None = None
    roa: float | None = None
    roe: float | None = None
    pretax_margin: float | None = None
    book_value_per_share: float | None = None
    quarterly_eps: list[CompanyFinancialHighlightEpsOut]
    annual_eps: list[CompanyFinancialHighlightEpsOut]
    data_date: date | None = None


class CompanyCalendarEventOut(BaseModel):
    section_key: str
    event_name: str
    event_date: date | None = None
    event_end_date: date | None = None
    event_value_text: str | None = None
    data_date: date | None = None
