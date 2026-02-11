from __future__ import annotations

from datetime import datetime
from sqlalchemy import ForeignKey, UniqueConstraint
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
