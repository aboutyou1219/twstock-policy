from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import EtlRun
from etl.daily_prices import (
    _parse_date,
    fetch_finmind_daily_prices,
    resolve_date_range,
    upsert_daily_prices,
)
from etl.ticker_universe import load_ticker_universe


@dataclass
class BatchStats:
    processed: int = 0
    fetched_rows: int = 0
    inserted_rows: int = 0
    errors: int = 0


def _start_run(db: Session, endpoint: str) -> int:
    run = EtlRun(
        endpoint=endpoint,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    return run.id


def _finish_run(db: Session, run_id: int, stats: BatchStats) -> None:
    status = "success" if stats.errors == 0 else "partial"
    error_msg = None if stats.errors == 0 else f"errors={stats.errors}"
    db.execute(
        text(
            """
            UPDATE etl_runs
            SET status = :status,
                finished_at = :finished_at,
                rows_fetched = :rows_fetched,
                rows_upserted = :rows_upserted,
                error = :error
            WHERE id = :id
            """
        ),
        {
            "status": status,
            "finished_at": datetime.utcnow(),
            "rows_fetched": stats.fetched_rows,
            "rows_upserted": stats.inserted_rows,
            "error": error_msg,
            "id": run_id,
        },
    )


def crawl(
    db: Session,
    tickers: Iterable[str],
    stats: BatchStats,
    *,
    from_date: date | None,
    to_date: date | None,
    latest: bool,
    commit_every: int = 20,
    request_interval_seconds: float = 15,
    max_retries: int = 3,
    retry_sleep_seconds: float = 300,
) -> None:
    start, end = resolve_date_range(from_date=from_date, to_date=to_date, latest=latest)
    pending = 0
    for ticker in tickers:
        rows = []
        for attempt in range(1, max_retries + 1):
            try:
                rows = fetch_finmind_daily_prices(ticker, start, end)
                break
            except Exception as exc:
                if attempt >= max_retries:
                    stats.errors += 1
                    print(f"[warn] daily price fetch failed for {ticker}: {exc}")
                    rows = []
                    break
                print(
                    f"[warn] daily price fetch failed for {ticker} "
                    f"(attempt {attempt}/{max_retries}): {exc}; "
                    f"sleeping {retry_sleep_seconds}s"
                )
                time.sleep(retry_sleep_seconds)

        stats.fetched_rows += len(rows)
        stats.inserted_rows += upsert_daily_prices(db, rows)
        stats.processed += 1
        pending += 1

        if pending >= commit_every:
            db.commit()
            pending = 0
        if stats.processed % 10 == 0:
            print(f"processed {stats.processed} tickers")

        if request_interval_seconds > 0:
            time.sleep(request_interval_seconds)

    if pending:
        db.commit()


def run(
    *,
    run_all: bool,
    ticker: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    latest: bool = False,
    commit_every: int = 20,
    request_interval_seconds: float = 15,
    max_retries: int = 3,
    retry_sleep_seconds: float = 300,
) -> BatchStats:
    if ticker:
        tickers = [ticker]
    elif run_all:
        tickers = load_ticker_universe()
    else:
        raise ValueError("use ticker or run_all")

    endpoint = "daily_prices_batch"
    if ticker:
        endpoint = f"daily_prices_batch:{ticker}"
    if latest:
        endpoint += ":latest"

    stats = BatchStats()
    with SessionLocal() as db:
        run_id = _start_run(db, endpoint=endpoint)
        crawl(
            db,
            tickers,
            stats,
            from_date=from_date,
            to_date=to_date,
            latest=latest,
            commit_every=commit_every,
            request_interval_seconds=request_interval_seconds,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        _finish_run(db, run_id, stats)
        db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily OHLCV price batch ETL")
    parser.add_argument("--ticker", help="crawl a single ticker, e.g. 2330")
    parser.add_argument("--all", action="store_true", help="crawl all tickers from ticker_universe")
    parser.add_argument("--latest", action="store_true", help="crawl the recent trading window")
    parser.add_argument("--from-date", dest="from_date", help="start date in YYYY-MM-DD")
    parser.add_argument("--to-date", dest="to_date", help="end date in YYYY-MM-DD")
    parser.add_argument("--commit-every", type=int, default=20, help="commit interval")
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=15,
        help="sleep between FinMind requests; 15s is about 240 requests/hour",
    )
    parser.add_argument("--max-retries", type=int, default=3, help="retries per ticker")
    parser.add_argument(
        "--retry-sleep-seconds",
        type=float,
        default=300,
        help="sleep before retry after a failed request",
    )
    args = parser.parse_args()

    if not args.ticker and not args.all:
        parser.error("use --ticker or --all")

    stats = run(
        run_all=args.all,
        ticker=args.ticker,
        from_date=_parse_date(args.from_date),
        to_date=_parse_date(args.to_date),
        latest=args.latest,
        commit_every=args.commit_every,
        request_interval_seconds=args.request_interval_seconds,
        max_retries=args.max_retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )
    print("--- Daily Prices Batch Report ---")
    print(f"tickers_processed={stats.processed}")
    print(f"rows_fetched={stats.fetched_rows}")
    print(f"rows_inserted={stats.inserted_rows}")
    print(f"errors={stats.errors}")


if __name__ == "__main__":
    main()
