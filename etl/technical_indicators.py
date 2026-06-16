from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import DailyPrice, DailyTechnicalIndicator
from etl.daily_prices import _parse_date, resolve_date_range
from etl.ticker_universe import load_ticker_universe

INDICATOR_COLUMNS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ma120",
    "ma240",
    "volume_ma5",
    "volume_ma20",
    "rsi14",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "k9",
    "d9",
    "bb_mid",
    "bb_upper",
    "bb_lower",
    "return_1d",
    "return_5d",
    "return_20d",
    "return_60d",
    "high_52w",
    "low_52w",
]


@dataclass
class IndicatorStats:
    processed: int = 0
    price_rows: int = 0
    indicator_rows: int = 0
    errors: int = 0


def _clean_number(value) -> float | None:
    if pd.isna(value):
        return None
    if not math.isfinite(float(value)):
        return None
    return round(float(value), 4)


def fetch_price_frame(db: Session, ticker: str, *, to_date: date | None = None) -> pd.DataFrame:
    stmt = (
        select(
            DailyPrice.ticker,
            DailyPrice.trade_date,
            DailyPrice.open_price,
            DailyPrice.high_price,
            DailyPrice.low_price,
            DailyPrice.close_price,
            DailyPrice.volume,
        )
        .where(DailyPrice.ticker == ticker)
        .order_by(DailyPrice.trade_date.asc())
    )
    if to_date is not None:
        stmt = stmt.where(DailyPrice.trade_date <= to_date)

    rows = db.execute(stmt).mappings().all()
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    for column in ["open_price", "high_price", "low_price", "close_price", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def calculate_indicators(
    prices: pd.DataFrame,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    if prices.empty:
        return []

    df = prices.sort_values("trade_date").copy()
    close = df["close_price"]
    high = df["high_price"]
    low = df["low_price"]
    volume = df["volume"]

    for window in [5, 10, 20, 60, 120, 240]:
        df[f"ma{window}"] = close.rolling(window=window, min_periods=window).mean()

    df["volume_ma5"] = volume.rolling(window=5, min_periods=5).mean()
    df["volume_ma20"] = volume.rolling(window=20, min_periods=20).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss
    df["rsi14"] = 100 - (100 / (1 + rs))
    df.loc[avg_loss == 0, "rsi14"] = 100

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["macd_hist"] = df["macd_dif"] - df["macd_dea"]

    rolling_low = low.rolling(window=9, min_periods=9).min()
    rolling_high = high.rolling(window=9, min_periods=9).max()
    rsv = ((close - rolling_low) / (rolling_high - rolling_low)) * 100
    df["k9"] = rsv.ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()
    df["d9"] = df["k9"].ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()

    df["bb_mid"] = df["ma20"]
    bb_std = close.rolling(window=20, min_periods=20).std()
    df["bb_upper"] = df["bb_mid"] + (bb_std * 2)
    df["bb_lower"] = df["bb_mid"] - (bb_std * 2)

    for window in [1, 5, 20, 60]:
        df[f"return_{window}d"] = close.pct_change(periods=window) * 100

    df["high_52w"] = high.rolling(window=252, min_periods=1).max()
    df["low_52w"] = low.rolling(window=252, min_periods=1).min()

    if from_date is not None:
        df = df[df["trade_date"] >= from_date]
    if to_date is not None:
        df = df[df["trade_date"] <= to_date]

    rows = []
    for _, item in df.iterrows():
        row = {
            "ticker": item["ticker"],
            "trade_date": item["trade_date"],
            "source": "derived",
        }
        for column in INDICATOR_COLUMNS:
            row[column] = _clean_number(item[column])
        rows.append(row)
    return rows


def upsert_daily_technical_indicators(db: Session, rows: Iterable[dict]) -> int:
    count = 0
    for row in rows:
        stmt = (
            insert(DailyTechnicalIndicator)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[
                    DailyTechnicalIndicator.ticker,
                    DailyTechnicalIndicator.trade_date,
                ],
                set_={
                    **{column: row.get(column) for column in INDICATOR_COLUMNS},
                    "source": row.get("source", "derived"),
                    "fetched_at": func.now(),
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_for_tickers(
    tickers: Iterable[str],
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    latest: bool = False,
    commit_every: int = 20,
) -> IndicatorStats:
    start, end = resolve_date_range(from_date=from_date, to_date=to_date, latest=latest)
    stats = IndicatorStats()
    pending = 0
    with SessionLocal() as db:
        for ticker in tickers:
            try:
                prices = fetch_price_frame(db, ticker, to_date=end)
                stats.price_rows += len(prices)
                rows = calculate_indicators(prices, from_date=start, to_date=end)
                stats.indicator_rows += upsert_daily_technical_indicators(db, rows)
            except Exception as exc:
                stats.errors += 1
                print(f"[warn] technical indicator calculation failed for {ticker}: {exc}")

            stats.processed += 1
            pending += 1
            if pending >= commit_every:
                db.commit()
                pending = 0
            if stats.processed % 10 == 0:
                print(f"processed {stats.processed} tickers")

        if pending:
            db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily technical indicator calculator")
    parser.add_argument("--ticker", help="calculate a single ticker, e.g. 2330")
    parser.add_argument("--all", action="store_true", help="calculate all tickers from ticker_universe")
    parser.add_argument("--latest", action="store_true", help="calculate the recent trading window")
    parser.add_argument("--from-date", dest="from_date", help="start date in YYYY-MM-DD")
    parser.add_argument("--to-date", dest="to_date", help="end date in YYYY-MM-DD")
    parser.add_argument("--commit-every", type=int, default=20, help="commit interval")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker]
    elif args.all:
        tickers = load_ticker_universe()
    else:
        parser.error("use --ticker or --all")

    stats = run_for_tickers(
        tickers,
        from_date=_parse_date(args.from_date),
        to_date=_parse_date(args.to_date),
        latest=args.latest,
        commit_every=args.commit_every,
    )
    print("--- Daily Technical Indicators Report ---")
    print(f"tickers_processed={stats.processed}")
    print(f"price_rows_read={stats.price_rows}")
    print(f"indicator_rows_upserted={stats.indicator_rows}")
    print(f"errors={stats.errors}")


if __name__ == "__main__":
    main()
