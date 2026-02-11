from __future__ import annotations

import re
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import EpsQuarter
from .http import get_text

YAHOO_EPS_URL = "https://tw.stock.yahoo.com/quote/{ticker}/eps"
EPS_PATTERN = re.compile(r"^(\d{4})\s+Q([1-4])$")


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
    m = EPS_PATTERN.match(value.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _extract_row_cells(row) -> tuple[str | None, list[str]]:
    period_text = None
    period_cell = row.select_one("div.W\(112px\)")
    if period_cell:
        period_text = period_cell.get_text(strip=True)

    cells: list[str] = []
    for span in row.select("span"):
        text = span.get_text(strip=True)
        if text:
            cells.append(text)
    return period_text, cells


def fetch_yahoo_eps(ticker: str) -> list[dict]:
    try:
        html = get_text(YAHOO_EPS_URL.format(ticker=ticker), timeout=30)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (404, 429):
            if exc.response.status_code == 404:
                print(f"[warn] yahoo eps not found for {ticker}")
            else:
                print(f"[warn] yahoo eps rate limited for {ticker}")
            return []
        raise
    except requests.RequestException as exc:
        print(f"[warn] yahoo eps request failed for {ticker}: {exc}")
        return []

    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section#qsp-eps-table")
    if section is None:
        return []

    rows = []
    for row in section.select("div.table-body-wrapper ul > li"):
        period_text, cells = _extract_row_cells(row)
        if len(cells) < 4:
            continue

        period = _parse_period(period_text or "")
        if period is None:
            continue

        year, quarter = period
        row_data = {
            "ticker": ticker,
            "fiscal_year": year,
            "fiscal_quarter": quarter,
            "eps": _parse_number(cells[0]),
            "qoq_pct": _parse_number(cells[1]),
            "yoy_pct": _parse_number(cells[2]),
            "avg_price": _parse_number(cells[3]),
        }
        rows.append(row_data)
    return rows


def upsert_yahoo_eps(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(EpsQuarter)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[EpsQuarter.ticker, EpsQuarter.fiscal_year, EpsQuarter.fiscal_quarter],
                set_={
                    "eps": row.get("eps"),
                    "qoq_pct": row.get("qoq_pct"),
                    "yoy_pct": row.get("yoy_pct"),
                    "avg_price": row.get("avg_price"),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_yahoo_eps_sync(ticker: str) -> int:
    from api.db import SessionLocal

    rows = fetch_yahoo_eps(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_eps(db, rows)
        db.commit()
    return count


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_eps_sync(target)
    print(f"inserted {inserted} rows for {target}")
