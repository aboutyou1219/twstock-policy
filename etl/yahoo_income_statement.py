from __future__ import annotations

import re
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import IncomeStatementQuarter
from .http import get_text

YAHOO_INCOME_URL = "https://tw.stock.yahoo.com/quote/{ticker}/income-statement"
PERIOD_PATTERN = re.compile(r"^(\d{4})\s+Q([1-4])$")

LABEL_MAP = {
    "營業收入": "revenue",
    "營業毛利": "gross_profit",
    "營業費用": "operating_expense",
    "營業利益": "operating_income",
    "稅後淨利": "net_income",
}


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


def _parse_period(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    m = PERIOD_PATTERN.match(value.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _extract_periods(section) -> list[tuple[int, int]]:
    periods: list[tuple[int, int]] = []
    header = section.select_one("div.table-header-wrapper")
    if not header:
        return periods

    for cell in header.select("div"):
        text = cell.get_text(strip=True)
        if not text:
            continue
        parsed = _parse_period(text)
        if parsed:
            periods.append(parsed)
    return periods


def _extract_row(section) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    for row in section.select("div.table-body-wrapper ul > li"):
        label_cell = row.select_one("div.W\(80px\) span")
        if not label_cell:
            continue
        label = label_cell.get_text(strip=True)
        value_cells = row.select("div.Miw\(144px\) span")
        values = [v.get_text(strip=True) for v in value_cells]
        rows.append((label, values))
    return rows


def fetch_yahoo_income_statement(ticker: str) -> list[dict]:
    try:
        html = get_text(YAHOO_INCOME_URL.format(ticker=ticker), timeout=30)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (404, 429):
            if exc.response.status_code == 404:
                print(f"[warn] yahoo income not found for {ticker}")
            else:
                print(f"[warn] yahoo income rate limited for {ticker}")
            return []
        raise
    except requests.RequestException as exc:
        print(f"[warn] yahoo income request failed for {ticker}: {exc}")
        return []

    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section#qsp-income-statement-table")
    if section is None:
        return []

    periods = _extract_periods(section)
    if not periods:
        return []

    data: dict[tuple[int, int], dict] = {p: {"ticker": ticker, "fiscal_year": p[0], "fiscal_quarter": p[1]} for p in periods}

    for label, values in _extract_row(section):
        field = LABEL_MAP.get(label)
        if not field:
            continue
        for idx, period in enumerate(periods):
            if idx >= len(values):
                continue
            data[period][field] = _parse_number(values[idx])

    return list(data.values())


def upsert_yahoo_income_statement(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(IncomeStatementQuarter)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[
                    IncomeStatementQuarter.ticker,
                    IncomeStatementQuarter.fiscal_year,
                    IncomeStatementQuarter.fiscal_quarter,
                ],
                set_={
                    "revenue": row.get("revenue"),
                    "gross_profit": row.get("gross_profit"),
                    "operating_expense": row.get("operating_expense"),
                    "operating_income": row.get("operating_income"),
                    "net_income": row.get("net_income"),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_yahoo_income_sync(ticker: str) -> int:
    from api.db import SessionLocal

    rows = fetch_yahoo_income_statement(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_income_statement(db, rows)
        db.commit()
    return count


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_income_sync(target)
    print(f"inserted {inserted} rows for {target}")
