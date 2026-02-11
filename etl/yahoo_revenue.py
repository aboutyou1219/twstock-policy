from __future__ import annotations

from datetime import date
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import MonthlyRevenue
from .http import get_text

YAHOO_REVENUE_URL = "https://tw.stock.yahoo.com/quote/{ticker}/revenue"


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    v = value.strip().replace(",", "")
    if v in ("", "-", "--", "—"):
        return None
    if v.endswith("%"):
        v = v[:-1].strip()
    try:
        return float(v)
    except ValueError:
        return None


def _parse_period(value: str) -> date | None:
    if not value or "/" not in value:
        return None
    y, m = value.split("/", 1)
    try:
        return date(int(y), int(m), 1)
    except ValueError:
        return None


def _extract_row_cells(row) -> tuple[str | None, list[str]]:
    period_text = None
    period_cell = row.select_one("div.W\\(65px\\)")
    if period_cell:
        period_text = period_cell.get_text(strip=True)

    cells: list[str] = []
    for span in row.select("span"):
        text = span.get_text(strip=True)
        if text:
            cells.append(text)
    return period_text, cells


def fetch_yahoo_monthly_revenue(ticker: str) -> list[dict]:
    try:
        html = get_text(YAHOO_REVENUE_URL.format(ticker=ticker), timeout=30)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (404, 429):
            if exc.response.status_code == 404:
                print(f"[warn] yahoo revenue not found for {ticker}")
            else:
                print(f"[warn] yahoo revenue rate limited for {ticker}")
            return []
        raise
    except requests.RequestException as exc:
        print(f"[warn] yahoo revenue request failed for {ticker}: {exc}")
        return []
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section#qsp-revenue-table")
    if section is None:
        return []

    rows = []
    for row in section.select("div.table-body-wrapper ul > li"):
        period_text, cells = _extract_row_cells(row)
        if len(cells) < 7:
            continue

        period = _parse_period(period_text or "")
        if period is None:
            continue

        row_data = {
            "ticker": ticker,
            "period": period,
            "month_revenue": _parse_number(cells[0]),
            "month_mom_pct": _parse_number(cells[1]),
            "month_prev_year_revenue": _parse_number(cells[2]),
            "month_yoy_pct": _parse_number(cells[3]),
            "cum_revenue": _parse_number(cells[4]),
            "cum_prev_year_revenue": _parse_number(cells[5]),
            "cum_yoy_pct": _parse_number(cells[6]),
        }
        rows.append(row_data)
    return rows


def upsert_yahoo_monthly_revenue(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(MonthlyRevenue)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[MonthlyRevenue.ticker, MonthlyRevenue.period],
                set_={
                    "month_revenue": row.get("month_revenue"),
                    "month_mom_pct": row.get("month_mom_pct"),
                    "month_prev_year_revenue": row.get("month_prev_year_revenue"),
                    "month_yoy_pct": row.get("month_yoy_pct"),
                    "cum_revenue": row.get("cum_revenue"),
                    "cum_prev_year_revenue": row.get("cum_prev_year_revenue"),
                    "cum_yoy_pct": row.get("cum_yoy_pct"),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_yahoo_monthly_revenue_sync(ticker: str) -> int:
    from api.db import SessionLocal

    rows = fetch_yahoo_monthly_revenue(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_monthly_revenue(db, rows)
        db.commit()
    return count


def run_yahoo_monthly_revenue_batch(tickers: Iterable[str]) -> int:
    from api.db import SessionLocal

    total = 0
    processed = 0
    with SessionLocal() as db:
        for ticker in tickers:
            rows = fetch_yahoo_monthly_revenue(ticker)
            total += upsert_yahoo_monthly_revenue(db, rows)
            db.commit()
            processed += 1
            if processed % 100 == 0:
                print(f"processed {processed} tickers")
    return total


if __name__ == "__main__":
    import sys
    import twstock

    if len(sys.argv) < 2:
        target = "2330"
        inserted = run_yahoo_monthly_revenue_sync(target)
        print(f"inserted {inserted} rows for {target}")
        raise SystemExit(0)

    target = sys.argv[1].strip().lower()
    if target == "all":
        tickers = sorted([k for k in twstock.codes.keys() if k.isdigit()])
        inserted = run_yahoo_monthly_revenue_batch(tickers)
        print(f"inserted {inserted} rows for {len(tickers)} tickers")
    else:
        inserted = run_yahoo_monthly_revenue_sync(sys.argv[1])
        print(f"inserted {inserted} rows for {sys.argv[1]}")
