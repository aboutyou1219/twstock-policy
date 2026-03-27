from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.exc import SQLAlchemyError
import twstock
from datetime import date

from .db import get_db
from .models import (
    BalanceSheetQuarter,
    CashFlowQuarter,
    Company,
    CompanyCalendarEvent,
    CompanyDividendSummary,
    CompanyFinancialHighlight,
    CompanyFinancialHighlightEps,
    CompanyProfile,
    EpsQuarter,
    FinancialQuarter,
    IncomeStatementQuarter,
    IndicatorQuarter,
    MonthlyRevenue,
    EtlRun,
)
from .schemas import (
    CompanyCalendarEventOut,
    CompanyDividendSummaryOut,
    CompanyFinancialHighlightsOut,
    CompanyFinancialHighlightEpsOut,
    CompanyProfileOut,
    MonthlyRevenueOut,
    ScreenMetadataOut,
    ScreenResponseOut,
    ScreeningRequest,
)

router = APIRouter()


def _latest_profile_subquery():
    return (
        select(
            CompanyProfile.ticker.label("ticker"),
            CompanyProfile.market.label("market"),
            CompanyProfile.group_name.label("group_name"),
            CompanyProfile.industry.label("industry"),
            CompanyProfile.share_capital.label("share_capital"),
            CompanyProfile.market_cap_million_twd.label("market_cap_million_twd"),
            CompanyProfile.company_name.label("company_name"),
            func.row_number()
            .over(
                partition_by=CompanyProfile.ticker,
                order_by=(CompanyProfile.data_date.desc(), CompanyProfile.fetched_at.desc()),
            )
            .label("rn"),
        )
        .subquery()
    )


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
        profile_subq = _latest_profile_subquery()
        highlight_subq = (
            select(
                CompanyFinancialHighlight.ticker.label("ticker"),
                CompanyFinancialHighlight.roe.label("roe"),
                CompanyFinancialHighlight.roa.label("roa"),
                CompanyFinancialHighlight.book_value_per_share.label("book_value_per_share"),
                func.row_number()
                .over(
                    partition_by=CompanyFinancialHighlight.ticker,
                    order_by=(
                        CompanyFinancialHighlight.data_date.desc(),
                        CompanyFinancialHighlight.fiscal_year.desc(),
                        CompanyFinancialHighlight.fiscal_quarter.desc(),
                        CompanyFinancialHighlight.fetched_at.desc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )

        dividend_subq = (
            select(
                CompanyDividendSummary.ticker.label("ticker"),
                CompanyDividendSummary.cash_dividend.label("cash_dividend"),
                func.row_number()
                .over(
                    partition_by=CompanyDividendSummary.ticker,
                    order_by=(CompanyDividendSummary.data_date.desc(), CompanyDividendSummary.fetched_at.desc()),
                )
                .label("rn"),
            )
            .subquery()
        )

        ex_dividend_subq = (
            select(
                CompanyCalendarEvent.ticker.label("ticker"),
                func.min(CompanyCalendarEvent.event_date).label("upcoming_ex_dividend_date"),
            )
            .where(
                CompanyCalendarEvent.section_key == "ex_dividend",
                CompanyCalendarEvent.event_name == "除息日期",
                CompanyCalendarEvent.event_date >= func.current_date(),
            )
            .group_by(CompanyCalendarEvent.ticker)
            .subquery()
        )

        latest_income_subq = (
            select(
                IncomeStatementQuarter.ticker.label("ticker"),
                IncomeStatementQuarter.fiscal_year.label("fiscal_year"),
                IncomeStatementQuarter.fiscal_quarter.label("fiscal_quarter"),
                IncomeStatementQuarter.revenue.label("revenue"),
                IncomeStatementQuarter.gross_profit.label("gross_profit"),
                IncomeStatementQuarter.operating_income.label("operating_income"),
                IncomeStatementQuarter.source.label("source"),
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
                profile_subq.c.company_name,
                profile_subq.c.market,
                profile_subq.c.group_name,
                profile_subq.c.share_capital.label("share_capital"),
                profile_subq.c.market_cap_million_twd.label("market_cap_million_twd"),
                profile_subq.c.industry.label("profile_industry"),
                gross_margin_expr,
                operating_margin_expr,
                revenue_subq.c.month_yoy_pct,
                revenue_subq.c.period.label("latest_month"),
                eps_subq.c.eps,
                gross_margin_yoy_delta,
                highlight_subq.c.roe,
                highlight_subq.c.roa,
                highlight_subq.c.book_value_per_share,
                dividend_subq.c.cash_dividend,
                ex_dividend_subq.c.upcoming_ex_dividend_date,
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
            .outerjoin(
                profile_subq,
                (profile_subq.c.ticker == latest_income_subq.c.ticker) & (profile_subq.c.rn == 1),
            )
            .outerjoin(
                highlight_subq,
                (highlight_subq.c.ticker == latest_income_subq.c.ticker) & (highlight_subq.c.rn == 1),
            )
            .outerjoin(
                dividend_subq,
                (dividend_subq.c.ticker == latest_income_subq.c.ticker) & (dividend_subq.c.rn == 1),
            )
            .outerjoin(
                ex_dividend_subq,
                ex_dividend_subq.c.ticker == latest_income_subq.c.ticker,
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
        if req.min_roe is not None:
            query = query.where(highlight_subq.c.roe >= req.min_roe)
        if req.min_roa is not None:
            query = query.where(highlight_subq.c.roa >= req.min_roa)
        if req.min_book_value_per_share is not None:
            query = query.where(highlight_subq.c.book_value_per_share >= req.min_book_value_per_share)
        if req.min_cash_dividend is not None:
            query = query.where(dividend_subq.c.cash_dividend >= req.min_cash_dividend)
        if req.market is not None:
            query = query.where(profile_subq.c.market == req.market)
        effective_share_capital_max = (
            req.share_capital_max if req.share_capital_max is not None else req.max_share_capital
        )
        if req.share_capital_min is not None:
            query = query.where(profile_subq.c.share_capital >= req.share_capital_min * 100000000)
        if effective_share_capital_max is not None:
            query = query.where(profile_subq.c.share_capital <= effective_share_capital_max * 100000000)
        if req.market_cap_min is not None:
            query = query.where(profile_subq.c.market_cap_million_twd >= req.market_cap_min)
        if req.market_cap_max is not None:
            query = query.where(profile_subq.c.market_cap_million_twd <= req.market_cap_max)
        if req.industry is not None:
            query = query.where(profile_subq.c.industry == req.industry)
        if req.upcoming_ex_dividend_within_days is not None:
            query = query.where(
                ex_dividend_subq.c.upcoming_ex_dividend_date.is_not(None),
                ex_dividend_subq.c.upcoming_ex_dividend_date
                <= (func.current_date() + req.upcoming_ex_dividend_within_days),
            )

        sort_map = {
            "gross_margin": gross_margin_expr,
            "operating_margin": operating_margin_expr,
            "revenue_yoy": revenue_subq.c.month_yoy_pct,
            "eps": eps_subq.c.eps,
            "gross_margin_yoy_delta": gross_margin_yoy_delta,
            "roe": highlight_subq.c.roe,
            "roa": highlight_subq.c.roa,
            "cash_dividend": dividend_subq.c.cash_dividend,
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
            industry = (
                getattr(row, "profile_industry", None)
                or (info.group if info is not None and getattr(info, "group", None) else None)
            )
            results.append(
                {
                    "ticker": row.ticker,
                    "name": row.company_name if getattr(row, "company_name", None) else (info.name if info is not None else row.ticker),
                    "market": getattr(row, "market", None) or (info.market if info is not None else None),
                    "industry": industry,
                    "group_name": getattr(row, "group_name", None),
                    "latest_month": row.latest_month,
                    "latest_quarter": row.latest_quarter,
                    "metrics": {
                        "gross_margin": row.gross_margin,
                        "operating_margin": row.operating_margin,
                        "revenue_yoy": row.month_yoy_pct,
                        "eps": row.eps,
                        "gross_margin_yoy_delta": row.gross_margin_yoy_delta,
                        "roe": row.roe,
                        "roa": row.roa,
                        "book_value_per_share": row.book_value_per_share,
                        "cash_dividend": row.cash_dividend,
                        "market_cap_million_twd": row.market_cap_million_twd,
                        "upcoming_ex_dividend_date": row.upcoming_ex_dividend_date,
                        "roi": None,
                        "share_capital_billion": (
                            (float(row.share_capital) / 100000000) if row.share_capital is not None else None
                        ),
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


@router.get("/v1/stocks/{ticker}/profile", response_model=CompanyProfileOut)
def stock_profile(ticker: str, db: Session = Depends(get_db)):
    try:
        profile = db.execute(
            select(CompanyProfile)
            .where(CompanyProfile.ticker == ticker)
            .order_by(CompanyProfile.data_date.desc(), CompanyProfile.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="ticker profile not found")

        return {
            "ticker": profile.ticker,
            "company_name": profile.company_name,
            "english_short_name": profile.english_short_name,
            "market": profile.market,
            "industry": profile.industry,
            "group_name": profile.group_name,
            "chairman": profile.chairman,
            "general_manager": profile.general_manager,
            "spokesperson": profile.spokesperson,
            "acting_spokesperson": profile.acting_spokesperson,
            "website": profile.website,
            "phone": profile.phone,
            "fax": profile.fax,
            "email": profile.email,
            "address": profile.address,
            "established_date": profile.established_date,
            "listed_date": profile.listed_date,
            "share_capital": profile.share_capital,
            "issued_common_shares": profile.issued_common_shares,
            "market_cap_million_twd": profile.market_cap_million_twd,
            "director_supervisor_holding_pct": profile.director_supervisor_holding_pct,
            "stock_transfer_agent": profile.stock_transfer_agent,
            "auditor": profile.auditor,
            "business_summary": profile.business_summary,
            "data_date": profile.data_date,
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/stocks/{ticker}/dividend-summary", response_model=CompanyDividendSummaryOut)
def stock_dividend_summary(ticker: str, db: Session = Depends(get_db)):
    try:
        row = db.execute(
            select(CompanyDividendSummary)
            .where(CompanyDividendSummary.ticker == ticker)
            .order_by(CompanyDividendSummary.data_date.desc(), CompanyDividendSummary.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="ticker dividend summary not found")
        return row
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/stocks/{ticker}/financial-highlights", response_model=CompanyFinancialHighlightsOut)
def stock_financial_highlights(ticker: str, db: Session = Depends(get_db)):
    try:
        row = db.execute(
            select(CompanyFinancialHighlight)
            .where(CompanyFinancialHighlight.ticker == ticker)
            .order_by(
                CompanyFinancialHighlight.data_date.desc(),
                CompanyFinancialHighlight.fiscal_year.desc(),
                CompanyFinancialHighlight.fiscal_quarter.desc(),
                CompanyFinancialHighlight.fetched_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="ticker financial highlights not found")

        eps_rows = (
            db.execute(
                select(CompanyFinancialHighlightEps)
                .where(
                    CompanyFinancialHighlightEps.ticker == ticker,
                    CompanyFinancialHighlightEps.data_date == row.data_date,
                )
                .order_by(
                    CompanyFinancialHighlightEps.series_type.asc(),
                    CompanyFinancialHighlightEps.display_order.asc(),
                )
            )
            .scalars()
            .all()
        )
        quarterly_eps = []
        annual_eps = []
        for eps_row in eps_rows:
            payload = CompanyFinancialHighlightEpsOut.model_validate(
                {
                    "series_type": eps_row.series_type,
                    "period_label": eps_row.period_label,
                    "fiscal_year": eps_row.fiscal_year,
                    "fiscal_quarter": eps_row.fiscal_quarter,
                    "eps": eps_row.eps,
                    "display_order": eps_row.display_order,
                }
            )
            if eps_row.series_type == "quarterly_eps":
                quarterly_eps.append(payload)
            else:
                annual_eps.append(payload)

        return {
            "ticker": row.ticker,
            "fiscal_year": row.fiscal_year,
            "fiscal_quarter": row.fiscal_quarter,
            "gross_margin": row.gross_margin,
            "operating_margin": row.operating_margin,
            "roa": row.roa,
            "roe": row.roe,
            "pretax_margin": row.pretax_margin,
            "book_value_per_share": row.book_value_per_share,
            "quarterly_eps": quarterly_eps,
            "annual_eps": annual_eps,
            "data_date": row.data_date,
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/stocks/{ticker}/calendar", response_model=list[CompanyCalendarEventOut])
def stock_calendar(ticker: str, db: Session = Depends(get_db)):
    try:
        latest_data_date = db.execute(
            select(func.max(CompanyCalendarEvent.data_date)).where(CompanyCalendarEvent.ticker == ticker)
        ).scalar_one_or_none()
        if latest_data_date is None:
            raise HTTPException(status_code=404, detail="ticker calendar not found")

        rows = (
            db.execute(
                select(CompanyCalendarEvent)
                .where(
                    CompanyCalendarEvent.ticker == ticker,
                    CompanyCalendarEvent.data_date == latest_data_date,
                )
                .order_by(
                    CompanyCalendarEvent.section_key.asc(),
                    CompanyCalendarEvent.event_date.asc().nullslast(),
                    CompanyCalendarEvent.event_name.asc(),
                )
            )
            .scalars()
            .all()
        )
        return rows
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/v1/screens/metadata", response_model=ScreenMetadataOut)
def screen_metadata(db: Session = Depends(get_db)):
    try:
        industries = sorted(
            filter(
                None,
                db.execute(
                    select(CompanyProfile.industry).distinct().where(CompanyProfile.industry.is_not(None))
                ).scalars().all(),
            )
        )
        markets = sorted(
            filter(
                None,
                db.execute(
                    select(CompanyProfile.market).distinct().where(CompanyProfile.market.is_not(None))
                ).scalars().all(),
            )
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
            "markets": markets,
            "default_filters": {
                "min_gross_margin": 30,
                "min_operating_margin": 15,
                "min_roi": None,
                "min_revenue_yoy": None,
                "min_eps": 2,
                "min_gross_margin_yoy_delta": 5,
                "min_roe": 8,
                "min_roa": 3,
                "min_book_value_per_share": None,
                "min_cash_dividend": None,
                "market": None,
                "share_capital_min": None,
                "share_capital_max": 10,
                "market_cap_min": None,
                "market_cap_max": None,
                "upcoming_ex_dividend_within_days": None,
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
