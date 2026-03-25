from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import EtlRun
from etl.ticker_universe import load_ticker_universe
from etl.yahoo_quarterly import fetch_yahoo_income_statement, upsert_yahoo_income_statement


@dataclass
class BatchStats:
    processed: int = 0
    fetched_rows: int = 0
    inserted_rows: int = 0
    top5_updated: int = 0
    top5_skipped: int = 0
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


def _all_tickers() -> list[str]:
    return load_ticker_universe()


def _db_top5(db: Session, ticker: str) -> list[tuple]:
    rows = db.execute(
        text(
            """
            SELECT fiscal_year, fiscal_quarter, revenue, gross_profit, operating_expense,
                   operating_income, net_income
            FROM income_statement_quarterly
            WHERE ticker = :t
            ORDER BY fiscal_year DESC, fiscal_quarter DESC
            LIMIT 5
            """
        ),
        {"t": ticker},
    ).all()
    return list(rows)


def _normalize_rows(rows: Iterable[dict]) -> list[tuple]:
    normalized = []
    for row in rows:
        normalized.append(
            (
                row.get("fiscal_year"),
                row.get("fiscal_quarter"),
                row.get("revenue"),
                row.get("gross_profit"),
                row.get("operating_expense"),
                row.get("operating_income"),
                row.get("net_income"),
            )
        )
    return normalized


def full_crawl(
    db: Session,
    tickers: Iterable[str],
    stats: BatchStats,
    commit_every: int = 20,
) -> dict[str, list[dict]]:
    cache: dict[str, list[dict]] = {}
    pending = 0
    for ticker in tickers:
        try:
            rows = fetch_yahoo_income_statement(ticker)
        except Exception as exc:
            stats.errors += 1
            print(f"[warn] fetch failed for {ticker}: {exc}")
            rows = []
        stats.fetched_rows += len(rows)
        cache[ticker] = rows
        stats.inserted_rows += upsert_yahoo_income_statement(db, rows)
        stats.processed += 1
        pending += 1
        if pending >= commit_every:
            db.commit()
            pending = 0
        if stats.processed % 10 == 0:
            print(f"processed {stats.processed} tickers")
    if pending:
        db.commit()
    return cache


def top5_crawl(
    db: Session,
    tickers: Iterable[str],
    cache: dict[str, list[dict]],
    stats: BatchStats,
    commit_every: int = 20,
) -> None:
    pending = 0
    for ticker in tickers:
        try:
            rows = cache.get(ticker)
            used_cache = rows is not None
            if rows is None:
                rows = fetch_yahoo_income_statement(ticker)
        except Exception as exc:
            stats.errors += 1
            print(f"[warn] fetch failed for {ticker}: {exc}")
            rows = []
            used_cache = False
        if not used_cache:
            stats.fetched_rows += len(rows)
            stats.processed += 1
        top5 = rows[:5]
        if not top5:
            continue
        existing = _db_top5(db, ticker)
        incoming = _normalize_rows(top5)
        if existing == incoming:
            stats.top5_skipped += 1
            continue
        stats.top5_updated += 1
        stats.inserted_rows += upsert_yahoo_income_statement(db, top5)
        pending += 1
        if pending >= commit_every:
            db.commit()
            pending = 0
    if pending:
        db.commit()


def run_single(ticker: str, run_top5: bool) -> BatchStats:
    stats = BatchStats()
    print(f"starting yahoo income batch for {ticker}...")
    with SessionLocal() as db:
        run_id = _start_run(db, endpoint=f"yahoo_income_batch:{ticker}")
        cache = full_crawl(db, [ticker], stats)
        if run_top5:
            top5_crawl(db, [ticker], cache, stats)
        _finish_run(db, run_id, stats)
        db.commit()
    print("--- Yahoo Income Batch Report ---")
    print(f"tickers_processed={stats.processed}")
    print(f"rows_fetched={stats.fetched_rows}")
    print(f"rows_inserted={stats.inserted_rows}")
    print(f"top5_updated={stats.top5_updated}")
    print(f"top5_skipped={stats.top5_skipped}")
    print(f"errors={stats.errors}")
    return stats


def run(run_all: bool, run_top5: bool) -> BatchStats:
    tickers = _all_tickers()
    stats = BatchStats()
    with SessionLocal() as db:
        run_id = _start_run(db, endpoint="yahoo_income_batch")
        cache: dict[str, list[dict]] = {}
        if run_all:
            cache = full_crawl(db, tickers, stats)
        if run_top5:
            top5_crawl(db, tickers, cache, stats)
        _finish_run(db, run_id, stats)
        db.commit()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yahoo income batch crawler")
    parser.add_argument("--all", action="store_true", help="crawl all income data")
    parser.add_argument("--top5", action="store_true", help="crawl top5 income only")
    parser.add_argument("--ticker", help="crawl a single ticker (e.g. 2337)")
    args = parser.parse_args()

    if not args.all and not args.top5 and not args.ticker:
        parser.error("use --all and/or --top5 or --ticker")

    if args.ticker:
        run_single(args.ticker, args.top5)
    elif args.all:
        print("starting yahoo income batch...")
        stats = run(True, args.top5)
        print("--- Yahoo Income Batch Report ---")
        print(f"tickers_processed={stats.processed}")
        print(f"rows_fetched={stats.fetched_rows}")
        print(f"rows_inserted={stats.inserted_rows}")
        print(f"top5_updated={stats.top5_updated}")
        print(f"top5_skipped={stats.top5_skipped}")
        print(f"errors={stats.errors}")
    else:
        print("starting yahoo income batch...")
        stats = run(False, True)
        print("--- Yahoo Income Batch Report ---")
        print(f"tickers_processed={stats.processed}")
        print(f"rows_fetched={stats.fetched_rows}")
        print(f"rows_inserted={stats.inserted_rows}")
        print(f"top5_updated={stats.top5_updated}")
        print(f"top5_skipped={stats.top5_skipped}")
        print(f"errors={stats.errors}")
