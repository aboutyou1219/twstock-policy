from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class FinancialQuarter(Base):
    __tablename__ = "financials_quarterly"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "fiscal_quarter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    revenue: Mapped[float | None]
    gross_profit: Mapped[float | None]
    operating_income: Mapped[float | None]
    net_income: Mapped[float | None]
    total_assets: Mapped[float | None]
    total_equity: Mapped[float | None]
    share_capital: Mapped[float | None]
    created_at: Mapped[datetime]

    company: Mapped[Company] = relationship(back_populates="financials")


class IndicatorQuarter(Base):
    __tablename__ = "indicators_quarterly"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year", "fiscal_quarter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    gross_margin: Mapped[float | None]
    operating_margin: Mapped[float | None]
    roi: Mapped[float | None]
    created_at: Mapped[datetime]

    company: Mapped[Company] = relationship(back_populates="indicators")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    market: Mapped[str | None]
    industry: Mapped[str | None]
    source: Mapped[str | None]
    raw_hash: Mapped[str | None]
    last_synced_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

    financials: Mapped[list[FinancialQuarter]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    indicators: Mapped[list[IndicatorQuarter]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str]
    status: Mapped[str]
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    rows_fetched: Mapped[int | None]
    rows_upserted: Mapped[int | None]
    error: Mapped[str | None]


class MonthlyRevenue(Base):
    __tablename__ = "monthly_revenue"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    period: Mapped[datetime]
    month_revenue: Mapped[float | None]
    month_mom_pct: Mapped[float | None]
    month_prev_year_revenue: Mapped[float | None]
    month_yoy_pct: Mapped[float | None]
    cum_revenue: Mapped[float | None]
    cum_prev_year_revenue: Mapped[float | None]
    cum_yoy_pct: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("ticker", "trade_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    trade_date: Mapped[date] = mapped_column(index=True)
    open_price: Mapped[float | None]
    high_price: Mapped[float | None]
    low_price: Mapped[float | None]
    close_price: Mapped[float | None]
    volume: Mapped[int | None]
    turnover: Mapped[float | None]
    transaction_count: Mapped[int | None]
    price_change: Mapped[float | None]
    market: Mapped[str | None]
    source: Mapped[str]
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime]


class DailyTechnicalIndicator(Base):
    __tablename__ = "daily_technical_indicators"
    __table_args__ = (UniqueConstraint("ticker", "trade_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    trade_date: Mapped[date] = mapped_column(index=True)
    ma5: Mapped[float | None]
    ma10: Mapped[float | None]
    ma20: Mapped[float | None]
    ma60: Mapped[float | None]
    ma120: Mapped[float | None]
    ma240: Mapped[float | None]
    volume_ma5: Mapped[float | None]
    volume_ma20: Mapped[float | None]
    rsi14: Mapped[float | None]
    macd_dif: Mapped[float | None]
    macd_dea: Mapped[float | None]
    macd_hist: Mapped[float | None]
    k9: Mapped[float | None]
    d9: Mapped[float | None]
    bb_mid: Mapped[float | None]
    bb_upper: Mapped[float | None]
    bb_lower: Mapped[float | None]
    return_1d: Mapped[float | None]
    return_5d: Mapped[float | None]
    return_20d: Mapped[float | None]
    return_60d: Mapped[float | None]
    high_52w: Mapped[float | None]
    low_52w: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class EpsQuarter(Base):
    __tablename__ = "eps_quarterly"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    eps: Mapped[float | None]
    qoq_pct: Mapped[float | None]
    yoy_pct: Mapped[float | None]
    avg_price: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class IncomeStatementQuarter(Base):
    __tablename__ = "income_statement_quarterly"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    revenue: Mapped[float | None]
    gross_profit: Mapped[float | None]
    operating_expense: Mapped[float | None]
    operating_income: Mapped[float | None]
    net_income: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class BalanceSheetQuarter(Base):
    __tablename__ = "balance_sheet_quarterly"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    total_assets: Mapped[float | None]
    total_liabilities: Mapped[float | None]
    equity: Mapped[float | None]
    current_assets: Mapped[float | None]
    current_liabilities: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class CashFlowQuarter(Base):
    __tablename__ = "cash_flow_quarterly"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    operating_cash_flow: Mapped[float | None]
    investing_cash_flow: Mapped[float | None]
    financing_cash_flow: Mapped[float | None]
    free_cash_flow: Mapped[float | None]
    net_cash_flow: Mapped[float | None]
    source: Mapped[str]
    fetched_at: Mapped[datetime]


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    yahoo_symbol: Mapped[str | None]
    company_name: Mapped[str]
    english_short_name: Mapped[str | None]
    market: Mapped[str | None]
    industry: Mapped[str | None]
    spokesperson: Mapped[str | None]
    acting_spokesperson: Mapped[str | None]
    chairman: Mapped[str | None]
    general_manager: Mapped[str | None]
    phone: Mapped[str | None]
    fax: Mapped[str | None]
    email: Mapped[str | None]
    website: Mapped[str | None]
    address: Mapped[str | None]
    stock_transfer_agent: Mapped[str | None]
    auditor: Mapped[str | None]
    group_name: Mapped[str | None]
    business_summary: Mapped[str | None]
    established_date: Mapped[date | None]
    listed_date: Mapped[date | None]
    share_capital: Mapped[float | None]
    issued_common_shares: Mapped[int | None]
    market_cap_million_twd: Mapped[float | None]
    director_supervisor_holding_pct: Mapped[float | None]
    data_date: Mapped[date]
    source: Mapped[str]
    source_url: Mapped[str | None]
    raw_hash: Mapped[str | None]
    fetched_at: Mapped[datetime]


class CompanyDividendSummary(Base):
    __tablename__ = "company_dividend_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    dividend_year: Mapped[int | None]
    cash_dividend: Mapped[float | None]
    earnings_stock_dividend: Mapped[float | None]
    capital_reserve_stock_dividend: Mapped[float | None]
    stock_dividend: Mapped[float | None]
    is_advance_notice: Mapped[bool]
    data_date: Mapped[date]
    source: Mapped[str]
    source_url: Mapped[str | None]
    raw_hash: Mapped[str | None]
    fetched_at: Mapped[datetime]


class CompanyFinancialHighlight(Base):
    __tablename__ = "company_financial_highlights"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int]
    gross_margin: Mapped[float | None]
    operating_margin: Mapped[float | None]
    roa: Mapped[float | None]
    roe: Mapped[float | None]
    pretax_margin: Mapped[float | None]
    book_value_per_share: Mapped[float | None]
    data_date: Mapped[date]
    source: Mapped[str]
    source_url: Mapped[str | None]
    raw_hash: Mapped[str | None]
    fetched_at: Mapped[datetime]


class CompanyFinancialHighlightEps(Base):
    __tablename__ = "company_financial_highlight_eps"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    series_type: Mapped[str]
    period_label: Mapped[str]
    fiscal_year: Mapped[int]
    fiscal_quarter: Mapped[int | None]
    eps: Mapped[float | None]
    display_order: Mapped[int]
    data_date: Mapped[date]
    source: Mapped[str]
    source_url: Mapped[str | None]
    raw_hash: Mapped[str | None]
    fetched_at: Mapped[datetime]


class CompanyCalendarEvent(Base):
    __tablename__ = "company_calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    section_key: Mapped[str]
    event_name: Mapped[str]
    event_date: Mapped[date | None]
    event_end_date: Mapped[date | None]
    event_value_text: Mapped[str | None]
    data_date: Mapped[date]
    source: Mapped[str]
    source_url: Mapped[str | None]
    raw_hash: Mapped[str | None]
    fetched_at: Mapped[datetime]
