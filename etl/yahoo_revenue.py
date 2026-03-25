from __future__ import annotations

import re
from datetime import date
from typing import Iterable

import requests
import twstock
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import MonthlyRevenue
from .http import get_text
from .ticker_universe import load_ticker_universe
from .yahoo_symbols import yahoo_quote_symbols

YAHOO_REVENUE_URL = "https://tw.stock.yahoo.com/quote/{ticker}/revenue"
PERIOD_PATTERN = re.compile(r"^\d{4}/\d{1,2}$")


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

    cells: list[str] = []
    for text in row.stripped_strings:
        if text:
            if period_text is None and PERIOD_PATTERN.fullmatch(text):
                period_text = text
                continue
            cells.append(text)
    return period_text, cells


def fetch_yahoo_monthly_revenue(ticker: str) -> list[dict]:
    html = None
    last_http_error: requests.HTTPError | None = None
    last_request_error: requests.RequestException | None = None
    tried_symbols = yahoo_quote_symbols(ticker)

    for yahoo_ticker in tried_symbols:
        try:
            html = get_text(YAHOO_REVENUE_URL.format(ticker=yahoo_ticker), timeout=30)
            break
        except requests.HTTPError as exc:
            last_http_error = exc
            if exc.response is not None and exc.response.status_code in (404, 429):
                continue
            raise
        except requests.RequestException as exc:
            last_request_error = exc
            continue

    if html is None:
        if last_http_error is not None and last_http_error.response is not None:
            status_code = last_http_error.response.status_code
            if status_code == 404:
                print(f"[warn] yahoo revenue not found for {ticker} (tried: {', '.join(tried_symbols)})")
                return []
            if status_code == 429:
                print(f"[warn] yahoo revenue rate limited for {ticker} (tried: {', '.join(tried_symbols)})")
                return []
        if last_request_error is not None:
            print(
                f"[warn] yahoo revenue request failed for {ticker} "
                f"(tried: {', '.join(tried_symbols)}): {last_request_error}"
            )
            return []
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

    if len(sys.argv) < 2:
        target = "2330"
        inserted = run_yahoo_monthly_revenue_sync(target)
        print(f"inserted {inserted} rows for {target}")
        raise SystemExit(0)

    target = sys.argv[1].strip().lower()
    if target == "all":
        try:
            twstock.__update_codes()
        except Exception as exc:
            print(f"[warn] update codes skipped: {exc}")
        tickers = load_ticker_universe()
        inserted = run_yahoo_monthly_revenue_batch(tickers)
        print(f"inserted {inserted} rows for {len(tickers)} tickers")
    else:
        inserted = run_yahoo_monthly_revenue_sync(sys.argv[1])
        print(f"inserted {inserted} rows for {sys.argv[1]}")
