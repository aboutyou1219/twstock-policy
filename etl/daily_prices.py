from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from typing import Iterable

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import DailyPrice

FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"
DEFAULT_SOURCE = "finmind"
DEFAULT_BACKFILL_START = date(2006, 1, 1)
LATEST_LOOKBACK_DAYS = 10


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_date_range(
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    latest: bool = False,
) -> tuple[date, date]:
    end = to_date or date.today()
    if latest:
        start = from_date or (end - timedelta(days=LATEST_LOOKBACK_DAYS))
    else:
        start = from_date or DEFAULT_BACKFILL_START
    if start > end:
        raise ValueError(f"from_date must be before to_date: {start} > {end}")
    return start, end


def fetch_finmind_daily_prices(
    ticker: str,
    from_date: date,
    to_date: date,
    *,
    token: str | None = None,
) -> list[dict]:
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": ticker,
        "start_date": from_date.isoformat(),
        "end_date": to_date.isoformat(),
    }
    auth_token = token or os.getenv("FINMIND_TOKEN")
    if auth_token:
        params["token"] = auth_token

    response = requests.get(FINMIND_DATA_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 200:
        raise RuntimeError(payload.get("msg") or f"FinMind request failed for {ticker}")

    rows = []
    for item in payload.get("data", []):
        trade_date = _parse_date(item.get("date"))
        if trade_date is None:
            continue
        rows.append(
            {
                "ticker": str(item.get("stock_id") or ticker),
                "trade_date": trade_date,
                "open_price": _to_float(item.get("open")),
                "high_price": _to_float(item.get("max")),
                "low_price": _to_float(item.get("min")),
                "close_price": _to_float(item.get("close")),
                "volume": _to_int(item.get("Trading_Volume")),
                "turnover": _to_float(item.get("Trading_money")),
                "transaction_count": _to_int(item.get("Trading_turnover")),
                "price_change": _to_float(item.get("spread")),
                "source": DEFAULT_SOURCE,
                "raw_payload": item,
            }
        )
    rows.sort(key=lambda row: row["trade_date"])
    return rows


def upsert_daily_prices(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(DailyPrice)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[DailyPrice.ticker, DailyPrice.trade_date],
                set_={
                    "open_price": row.get("open_price"),
                    "high_price": row.get("high_price"),
                    "low_price": row.get("low_price"),
                    "close_price": row.get("close_price"),
                    "volume": row.get("volume"),
                    "turnover": row.get("turnover"),
                    "transaction_count": row.get("transaction_count"),
                    "price_change": row.get("price_change"),
                    "market": row.get("market"),
                    "source": row.get("source", DEFAULT_SOURCE),
                    "raw_payload": row.get("raw_payload"),
                    "fetched_at": func.now(),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def get_latest_trade_date(db: Session, ticker: str) -> date | None:
    return db.execute(
        select(func.max(DailyPrice.trade_date)).where(DailyPrice.ticker == ticker)
    ).scalar_one_or_none()


def run_daily_price_sync(
    ticker: str,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    latest: bool = False,
) -> int:
    from api.db import SessionLocal

    start, end = resolve_date_range(from_date=from_date, to_date=to_date, latest=latest)
    rows = fetch_finmind_daily_prices(ticker, start, end)
    with SessionLocal() as db:
        count = upsert_daily_prices(db, rows)
        db.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily OHLCV price ETL")
    parser.add_argument("--ticker", help="crawl a single ticker, e.g. 2330")
    parser.add_argument("--all", action="store_true", help="crawl all tickers through daily_prices_batch")
    parser.add_argument("--latest", action="store_true", help="crawl the recent trading window")
    parser.add_argument("--from-date", dest="from_date", help="start date in YYYY-MM-DD")
    parser.add_argument("--to-date", dest="to_date", help="end date in YYYY-MM-DD")
    parser.add_argument("--commit-every", type=int, default=20, help="batch commit interval for --all")
    args = parser.parse_args()

    if args.all:
        from etl.daily_prices_batch import run

        stats = run(
            run_all=True,
            from_date=_parse_date(args.from_date),
            to_date=_parse_date(args.to_date),
            latest=args.latest,
            commit_every=args.commit_every,
        )
        print("--- Daily Prices Batch Report ---")
        print(f"tickers_processed={stats.processed}")
        print(f"rows_fetched={stats.fetched_rows}")
        print(f"rows_inserted={stats.inserted_rows}")
        print(f"errors={stats.errors}")
        return

    if not args.ticker:
        parser.error("use --ticker or --all")

    inserted = run_daily_price_sync(
        args.ticker,
        from_date=_parse_date(args.from_date),
        to_date=_parse_date(args.to_date),
        latest=args.latest,
    )
    print(f"inserted {inserted} daily price rows for {args.ticker}")


if __name__ == "__main__":
    main()
