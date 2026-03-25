from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError
import twstock

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
from .schemas import (
    MonthlyRevenueOut,
    ScreenMetadataOut,
    ScreenResponseOut,
    ScreeningRequest,
)

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
    sort_by: str = "gross_margin",
    sort_dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> ScreenResponseOut:
    try:
        latest_income_subq = (
            select(
                IncomeStatementQuarter.ticker.label("ticker"),
                IncomeStatementQuarter.fiscal_year.label("fiscal_year"),
                IncomeStatementQuarter.fiscal_quarter.label("fiscal_quarter"),
                IncomeStatementQuarter.revenue.label("revenue"),
                IncomeStatementQuarter.gross_profit.label("gross_profit"),
                IncomeStatementQuarter.operating_income.label("operating_income"),
                func.row_number()
                .over(
                    partition_by=IncomeStatementQuarter.ticker,
                    order_by=(
                        IncomeStatementQuarter.fiscal_year.desc(),
                        IncomeStatementQuarter.fiscal_quarter.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )
        prior_income = aliased(IncomeStatementQuarter)

        revenue_subq = (
            select(
                MonthlyRevenue.ticker.label("ticker"),
                MonthlyRevenue.period.label("period"),
                MonthlyRevenue.month_yoy_pct.label("month_yoy_pct"),
                func.row_number()
                .over(
                    partition_by=MonthlyRevenue.ticker,
                    order_by=MonthlyRevenue.period.desc(),
                )
                .label("rn"),
            )
            .subquery()
        )

        eps_subq = (
            select(
                EpsQuarter.ticker.label("ticker"),
                EpsQuarter.eps.label("eps"),
                EpsQuarter.fiscal_year.label("fiscal_year"),
                EpsQuarter.fiscal_quarter.label("fiscal_quarter"),
                func.row_number()
                .over(
                    partition_by=EpsQuarter.ticker,
                    order_by=(EpsQuarter.fiscal_year.desc(), EpsQuarter.fiscal_quarter.desc()),
                )
                .label("rn"),
            )
            .subquery()
        )

        gross_margin_expr = (
            latest_income_subq.c.gross_profit * 100.0 / func.nullif(latest_income_subq.c.revenue, 0)
        ).label("gross_margin")
        operating_margin_expr = (
            latest_income_subq.c.operating_income * 100.0 / func.nullif(latest_income_subq.c.revenue, 0)
        ).label("operating_margin")
        prior_gross_margin_expr = (
            prior_income.gross_profit * 100.0 / func.nullif(prior_income.revenue, 0)
        )
        gross_margin_yoy_delta = (
            gross_margin_expr - prior_gross_margin_expr
        ).label("gross_margin_yoy_delta")
        latest_quarter = (
            func.concat(
                latest_income_subq.c.fiscal_year,
                " Q",
                latest_income_subq.c.fiscal_quarter,
            )
        ).label("latest_quarter")

        query = (
            select(
                latest_income_subq.c.ticker,
                gross_margin_expr,
                operating_margin_expr,
                revenue_subq.c.month_yoy_pct,
                revenue_subq.c.period.label("latest_month"),
                eps_subq.c.eps,
                gross_margin_yoy_delta,
                latest_quarter,
            )
            .select_from(latest_income_subq)
            .outerjoin(
                prior_income,
                and_(
                    prior_income.ticker == latest_income_subq.c.ticker,
                    prior_income.fiscal_year == latest_income_subq.c.fiscal_year - 1,
                    prior_income.fiscal_quarter == latest_income_subq.c.fiscal_quarter,
                ),
            )
            .outerjoin(
                revenue_subq,
                (revenue_subq.c.ticker == latest_income_subq.c.ticker) & (revenue_subq.c.rn == 1),
            )
            .outerjoin(
                eps_subq,
                (eps_subq.c.ticker == latest_income_subq.c.ticker) & (eps_subq.c.rn == 1),
            )
            .where(latest_income_subq.c.rn == 1)
        )

        if req.min_gross_margin is not None:
            query = query.where(gross_margin_expr >= req.min_gross_margin)
        if req.min_operating_margin is not None:
            query = query.where(operating_margin_expr >= req.min_operating_margin)
        if req.min_revenue_yoy is not None:
            query = query.where(revenue_subq.c.month_yoy_pct >= req.min_revenue_yoy)
        if req.min_eps is not None:
            query = query.where(eps_subq.c.eps >= req.min_eps)
        if req.min_gross_margin_yoy_delta is not None:
            query = query.where(gross_margin_yoy_delta >= req.min_gross_margin_yoy_delta)

        sort_map = {
            "gross_margin": gross_margin_expr,
            "operating_margin": operating_margin_expr,
            "revenue_yoy": revenue_subq.c.month_yoy_pct,
            "eps": eps_subq.c.eps,
            "gross_margin_yoy_delta": gross_margin_yoy_delta,
        }
        sort_col = sort_map.get(sort_by, gross_margin_expr)
        if sort_dir.lower() == "asc":
            query = query.order_by(sort_col.asc().nullslast())
        else:
            query = query.order_by(sort_col.desc().nullslast())

        query = query.limit(limit).offset(offset)
        rows = db.execute(query).all()
        results = []
        for row in rows:
            info = twstock.codes.get(row.ticker)
            industry = info.group if info is not None and getattr(info, "group", None) else None
            if req.industry and industry != req.industry:
                continue
            results.append(
                {
                    "ticker": row.ticker,
                    "name": info.name if info is not None else row.ticker,
                    "industry": industry,
                    "latest_month": row.latest_month,
                    "latest_quarter": row.latest_quarter,
                    "metrics": {
                        "gross_margin": row.gross_margin,
                        "operating_margin": row.operating_margin,
                        "revenue_yoy": row.month_yoy_pct,
                        "eps": row.eps,
                        "gross_margin_yoy_delta": row.gross_margin_yoy_delta,
                        "roi": None,
                        "share_capital_billion": None,
                    },
                }
            )
        return {
            "count": len(results),
            "total": len(results),
            "limit": limit,
            "offset": offset,
            "items": results,
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/screens/metadata", response_model=ScreenMetadataOut)
def screen_metadata(db: Session = Depends(get_db)):
    try:
        industries = sorted(
            {
                info.group
                for code, info in twstock.codes.items()
                if code.isdigit()
                and len(code) == 4
                and info.type == "股票"
                and info.market in ["上市", "上櫃"]
                and getattr(info, "group", None)
            }
        )

        latest_month = db.execute(select(func.max(MonthlyRevenue.period))).scalar_one_or_none()
        latest_income_row = db.execute(
            select(IncomeStatementQuarter.fiscal_year, IncomeStatementQuarter.fiscal_quarter)
            .order_by(
                IncomeStatementQuarter.fiscal_year.desc(),
                IncomeStatementQuarter.fiscal_quarter.desc(),
            )
            .limit(1)
        ).first()

        latest_quarter = None
        if latest_income_row is not None:
            latest_quarter = f"{latest_income_row.fiscal_year} Q{latest_income_row.fiscal_quarter}"

        return {
            "industries": industries,
            "default_filters": {
                "min_gross_margin": 30,
                "min_operating_margin": 15,
                "min_roi": None,
                "min_revenue_yoy": None,
                "min_eps": 2,
                "min_gross_margin_yoy_delta": 5,
                "max_share_capital": None,
                "industry": None,
            },
            "data_as_of": {
                "latest_month": latest_month.isoformat() if latest_month is not None else None,
                "latest_quarter": latest_quarter,
            },
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/stocks/{ticker}/diagnostics")
def stock_diagnostics(ticker: str, db: Session = Depends(get_db)):
    try:
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

        if not max_years and not monthly_rows:
            raise HTTPException(status_code=404, detail="ticker not found")

        company = db.execute(select(Company).where(Company.ticker == ticker)).scalar_one_or_none()
        info = twstock.codes.get(ticker)

        return {
            "basic": {
                "ticker": ticker,
                "name": company.name if company is not None else (info.name if info is not None else ticker),
                "market": company.market if company is not None else (info.market if info is not None else None),
                "industry": company.industry if company is not None else (info.group if info is not None else None),
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
