from __future__ import annotations

import re
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import BalanceSheetQuarter
from .http import get_text

YAHOO_BALANCE_URL = "https://tw.stock.yahoo.com/quote/{ticker}/balance-sheet"
PERIOD_PATTERN = re.compile(r"^(\d{4})\s+Q([1-4])$")

LABEL_MAP = {
    "總資產": "total_assets",
    "總負債": "total_liabilities",
    "股東權益（淨值）": "equity",
    "流動資產": "current_assets",
    "流動負債": "current_liabilities",
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
        label_cell = row.select_one("div.W\(144px\) span")
        if not label_cell:
            continue
        label = label_cell.get_text(strip=True)
        value_cells = row.select("div.Miw\(144px\) span")
        values = [v.get_text(strip=True) for v in value_cells]
        rows.append((label, values))
    return rows


def fetch_yahoo_balance_sheet(ticker: str) -> list[dict]:
    try:
        html = get_text(YAHOO_BALANCE_URL.format(ticker=ticker), timeout=30)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (404, 429):
            if exc.response.status_code == 404:
                print(f"[warn] yahoo balance not found for {ticker}")
            else:
                print(f"[warn] yahoo balance rate limited for {ticker}")
            return []
        raise
    except requests.RequestException as exc:
        print(f"[warn] yahoo balance request failed for {ticker}: {exc}")
        return []

    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section#qsp-balance-sheet-table")
    if section is None:
        return []

    periods = _extract_periods(section)
    if not periods:
        return []

    data: dict[tuple[int, int], dict] = {
        p: {"ticker": ticker, "fiscal_year": p[0], "fiscal_quarter": p[1]} for p in periods
    }

    for label, values in _extract_row(section):
        field = LABEL_MAP.get(label)
        if not field:
            continue
        for idx, period in enumerate(periods):
            if idx >= len(values):
                continue
            data[period][field] = _parse_number(values[idx])

    return list(data.values())


def upsert_yahoo_balance_sheet(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(BalanceSheetQuarter)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[
                    BalanceSheetQuarter.ticker,
                    BalanceSheetQuarter.fiscal_year,
                    BalanceSheetQuarter.fiscal_quarter,
                ],
                set_={
                    "total_assets": row.get("total_assets"),
                    "total_liabilities": row.get("total_liabilities"),
                    "equity": row.get("equity"),
                    "current_assets": row.get("current_assets"),
                    "current_liabilities": row.get("current_liabilities"),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_yahoo_balance_sync(ticker: str) -> int:
    from api.db import SessionLocal

    rows = fetch_yahoo_balance_sheet(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_balance_sheet(db, rows)
        db.commit()
    return count


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_balance_sync(target)
    print(f"inserted {inserted} rows for {target}")
