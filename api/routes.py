from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError

from .db import get_db
from .models import (
    BalanceSheetQuarter,
    CashFlowQuarter,
    Company,
    EpsQuarter,
    FinancialQuarter,
    IncomeStatementQuarter,
    IndicatorQuarter,
    MonthlyRevenue,
    EtlRun,
)
from .schemas import MonthlyRevenueOut, ScreeningRequest

router = APIRouter()


@router.get("/monthly-revenue/{ticker}", response_model=list[MonthlyRevenueOut])
def monthly_revenue(ticker: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(MonthlyRevenue)
        .where(MonthlyRevenue.ticker == ticker)
        .order_by(MonthlyRevenue.period.desc())
    ).scalars().all()
    return rows


@router.post("/v1/stocks/screen")
def screen_companies(
    req: ScreeningRequest,
    db: Session = Depends(get_db),
    sort_by: str = "roi",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
):
    try:
        indicators_subq = (
            select(
                IndicatorQuarter,
                func.row_number()
                .over(
                    partition_by=IndicatorQuarter.company_id,
                    order_by=(
                        IndicatorQuarter.fiscal_year.desc(),
                        IndicatorQuarter.fiscal_quarter.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )
        indicators_latest = aliased(IndicatorQuarter, indicators_subq)

        financials_subq = (
            select(
                FinancialQuarter,
                func.row_number()
                .over(
                    partition_by=FinancialQuarter.company_id,
                    order_by=(
                        FinancialQuarter.fiscal_year.desc(),
                        FinancialQuarter.fiscal_quarter.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )
        financials_latest = aliased(FinancialQuarter, financials_subq)

        revenue_subq = (
            select(
                MonthlyRevenue,
                func.row_number()
                .over(
                    partition_by=MonthlyRevenue.ticker,
                    order_by=MonthlyRevenue.period.desc(),
                )
                .label("rn"),
            )
            .subquery()
        )
        revenue_latest = aliased(MonthlyRevenue, revenue_subq)

        query = (
            select(
                Company.ticker,
                Company.name,
                Company.industry,
                indicators_latest.gross_margin,
                indicators_latest.roi,
                indicators_latest.operating_margin,
                financials_latest.share_capital,
                revenue_latest.month_yoy_pct,
                revenue_latest.period.label("latest_month"),
            )
            .join(
                indicators_subq,
                (indicators_subq.c.company_id == Company.id) & (indicators_subq.c.rn == 1),
            )
            .join(
                revenue_subq,
                (revenue_subq.c.ticker == Company.ticker) & (revenue_subq.c.rn == 1),
            )
            .outerjoin(
                financials_subq,
                (financials_subq.c.company_id == Company.id) & (financials_subq.c.rn == 1),
            )
        )

        if req.min_gross_margin is not None:
            query = query.where(indicators_latest.gross_margin >= req.min_gross_margin)
        if req.min_roi is not None:
            query = query.where(indicators_latest.roi >= req.min_roi)
        if req.min_revenue_yoy is not None:
            query = query.where(revenue_latest.month_yoy_pct >= req.min_revenue_yoy)
        if req.max_share_capital is not None:
            max_capital = req.max_share_capital * 1_000_000_000
            query = query.where(financials_latest.share_capital <= max_capital)
        if req.industry is not None:
            query = query.where(Company.industry == req.industry)

        sort_map = {
            "gross_margin": indicators_latest.gross_margin,
            "roi": indicators_latest.roi,
            "operating_margin": indicators_latest.operating_margin,
            "revenue_yoy": revenue_latest.month_yoy_pct,
            "share_capital": financials_latest.share_capital,
        }
        sort_col = sort_map.get(sort_by, indicators_latest.roi)
        if sort_dir.lower() == "asc":
            query = query.order_by(sort_col.asc().nullslast())
        else:
            query = query.order_by(sort_col.desc().nullslast())

        query = query.limit(limit).offset(offset)
        rows = db.execute(query).all()
        results = []
        for row in rows:
            results.append(
                {
                    "ticker": row.ticker,
                    "name": row.name,
                    "industry": row.industry,
                    "gross_margin": row.gross_margin,
                    "roi": row.roi,
                    "operating_margin": row.operating_margin,
                    "revenue_yoy": row.month_yoy_pct,
                    "share_capital_billion": (
                        row.share_capital / 1_000_000_000 if row.share_capital is not None else None
                    ),
                    "latest_month": row.latest_month,
                }
            )
        return {
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "items": results,
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/stocks/{ticker}/diagnostics")
def stock_diagnostics(ticker: str, db: Session = Depends(get_db)):
    try:
        company = db.execute(select(Company).where(Company.ticker == ticker)).scalar_one_or_none()
        if company is None:
            raise HTTPException(status_code=404, detail="ticker not found")

        max_years = []
        for model in (IncomeStatementQuarter, BalanceSheetQuarter, CashFlowQuarter, EpsQuarter):
            max_year = db.execute(
                select(func.max(model.fiscal_year)).where(model.ticker == ticker)
            ).scalar_one_or_none()
            if max_year is not None:
                max_years.append(max_year)
        max_year = max(max_years) if max_years else None
        since_year = (max_year - 4) if max_year is not None else None

        def _quarterly_rows(model):
            q = select(model).where(model.ticker == ticker)
            if since_year is not None:
                q = q.where(model.fiscal_year >= since_year)
            return (
                db.execute(
                    q.order_by(model.fiscal_year.desc(), model.fiscal_quarter.desc())
                )
                .scalars()
                .all()
            )

        quarterly = {
            "income_statement": _quarterly_rows(IncomeStatementQuarter),
            "balance_sheet": _quarterly_rows(BalanceSheetQuarter),
            "cash_flow": _quarterly_rows(CashFlowQuarter),
            "eps": _quarterly_rows(EpsQuarter),
        }

        monthly_rows = (
            db.execute(
                select(MonthlyRevenue)
                .where(MonthlyRevenue.ticker == ticker)
                .order_by(MonthlyRevenue.period.desc())
                .limit(24)
            )
            .scalars()
            .all()
        )
        monthly_rows = list(reversed(monthly_rows))

        return {
            "basic": {
                "ticker": company.ticker,
                "name": company.name,
                "market": company.market,
                "industry": company.industry,
            },
            "quarterly": {
                "income_statement": quarterly["income_statement"],
                "balance_sheet": quarterly["balance_sheet"],
                "cash_flow": quarterly["cash_flow"],
                "eps": quarterly["eps"],
            },
            "monthly": {
                "revenue": monthly_rows,
            },
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/industry/{industry_name}/rankings")
def industry_rankings(
    industry_name: str,
    db: Session = Depends(get_db),
    metric: str = "operating_margin",
    limit: int = 50,
    offset: int = 0,
):
    try:
        indicators_subq = (
            select(
                IndicatorQuarter,
                func.row_number()
                .over(
                    partition_by=IndicatorQuarter.company_id,
                    order_by=(
                        IndicatorQuarter.fiscal_year.desc(),
                        IndicatorQuarter.fiscal_quarter.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )
        indicators_latest = aliased(IndicatorQuarter, indicators_subq)

        metric_map = {
            "gross_margin": indicators_latest.gross_margin,
            "operating_margin": indicators_latest.operating_margin,
            "roi": indicators_latest.roi,
        }
        metric_col = metric_map.get(metric, indicators_latest.operating_margin)

        avg_value = db.execute(
            select(func.avg(metric_col))
            .select_from(Company)
            .join(
                indicators_subq,
                (indicators_subq.c.company_id == Company.id) & (indicators_subq.c.rn == 1),
            )
            .where(Company.industry == industry_name)
        ).scalar_one_or_none()

        ranked_subq = (
            select(
                Company.ticker,
                Company.name,
                metric_col.label("metric_value"),
                func.rank().over(order_by=metric_col.desc()).label("rank"),
            )
            .join(
                indicators_subq,
                (indicators_subq.c.company_id == Company.id) & (indicators_subq.c.rn == 1),
            )
            .where(Company.industry == industry_name)
            .subquery()
        )

        rows = db.execute(
            select(ranked_subq)
            .order_by(ranked_subq.c.rank.asc())
            .limit(limit)
            .offset(offset)
        ).all()

        return {
            "industry": industry_name,
            "metric": metric,
            "average": avg_value,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "ticker": row.ticker,
                    "name": row.name,
                    "rank": row.rank,
                    "value": row.metric_value,
                }
                for row in rows
            ],
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/system/status")
def system_status(db: Session = Depends(get_db)):
    try:
        last_success = db.execute(
            select(func.max(EtlRun.finished_at)).where(EtlRun.status == "success")
        ).scalar_one_or_none()

        total_companies = db.execute(select(func.count(Company.id))).scalar_one()

        recent_runs = db.execute(
            select(
                EtlRun.endpoint,
                EtlRun.status,
                EtlRun.started_at,
                EtlRun.finished_at,
                EtlRun.error,
            )
            .order_by(EtlRun.started_at.desc())
            .limit(10)
        ).all()

        has_errors = any(run.error for run in recent_runs)

        return {
            "last_success_at": last_success,
            "total_companies": total_companies,
            "has_errors": has_errors,
            "recent_runs": [
                {
                    "endpoint": run.endpoint,
                    "status": run.status,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "error": run.error,
                }
                for run in recent_runs
            ],
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")
