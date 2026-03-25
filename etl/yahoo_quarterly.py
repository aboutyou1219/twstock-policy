from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Iterable, Literal

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import (
    BalanceSheetQuarter,
    CashFlowQuarter,
    EpsQuarter,
    IncomeStatementQuarter,
)
from .http import get_text
from .ticker_universe import load_ticker_universe
from .yahoo_symbols import yahoo_quote_symbols

QuarterlyDataset = Literal["eps", "income_statement", "balance_sheet", "cash_flow"]
ALL_QUARTERLY_DATASETS: tuple[QuarterlyDataset, ...] = (
    "eps",
    "income_statement",
    "balance_sheet",
    "cash_flow",
)
PERIOD_PATTERN = re.compile(r"^(\d{4})\s+Q([1-4])$")


@dataclass(frozen=True)
class RowListConfig:
    url: str
    section_selector: str
    period_cell_selector: str
    min_values: int
    fields: list[str]
    model: type
    conflict_columns: list[str]
    update_columns: list[str]


@dataclass(frozen=True)
class MatrixConfig:
    url: str
    section_selector: str
    label_map: dict[str, str]
    label_cell_selector: str
    value_cell_selector: str
    model: type
    conflict_columns: list[str]
    update_columns: list[str]


ROW_LIST_CONFIGS: dict[QuarterlyDataset, RowListConfig] = {
    "eps": RowListConfig(
        url="https://tw.stock.yahoo.com/quote/{ticker}/eps",
        section_selector="section#qsp-eps-table",
        period_cell_selector=r"div.W\(112px\)",
        min_values=4,
        fields=["eps", "qoq_pct", "yoy_pct", "avg_price"],
        model=EpsQuarter,
        conflict_columns=["ticker", "fiscal_year", "fiscal_quarter"],
        update_columns=["eps", "qoq_pct", "yoy_pct", "avg_price"],
    )
}


MATRIX_CONFIGS: dict[QuarterlyDataset, MatrixConfig] = {
    "income_statement": MatrixConfig(
        url="https://tw.stock.yahoo.com/quote/{ticker}/income-statement",
        section_selector="section#qsp-income-statement-table",
        label_map={
            "營業收入": "revenue",
            "營業毛利": "gross_profit",
            "營業費用": "operating_expense",
            "營業利益": "operating_income",
            "稅後淨利": "net_income",
        },
        label_cell_selector=r"div.W\(80px\) span",
        value_cell_selector=r"div.Miw\(144px\) span",
        model=IncomeStatementQuarter,
        conflict_columns=["ticker", "fiscal_year", "fiscal_quarter"],
        update_columns=[
            "revenue",
            "gross_profit",
            "operating_expense",
            "operating_income",
            "net_income",
        ],
    ),
    "balance_sheet": MatrixConfig(
        url="https://tw.stock.yahoo.com/quote/{ticker}/balance-sheet",
        section_selector="section#qsp-balance-sheet-table",
        label_map={
            "總資產": "total_assets",
            "總負債": "total_liabilities",
            "股東權益（淨值）": "equity",
            "流動資產": "current_assets",
            "流動負債": "current_liabilities",
        },
        label_cell_selector=r"div.W\(144px\) span",
        value_cell_selector=r"div.Miw\(144px\) span",
        model=BalanceSheetQuarter,
        conflict_columns=["ticker", "fiscal_year", "fiscal_quarter"],
        update_columns=[
            "total_assets",
            "total_liabilities",
            "equity",
            "current_assets",
            "current_liabilities",
        ],
    ),
    "cash_flow": MatrixConfig(
        url="https://tw.stock.yahoo.com/quote/{ticker}/cash-flow-statement",
        section_selector="section#qsp-cash-flow-statement-table",
        label_map={
            "營業現金流": "operating_cash_flow",
            "投資現金流": "investing_cash_flow",
            "融資現金流": "financing_cash_flow",
            "自由現金流": "free_cash_flow",
            "淨現金流": "net_cash_flow",
        },
        label_cell_selector=r"div.W\(120px\) span",
        value_cell_selector=r"div.Miw\(144px\) span",
        model=CashFlowQuarter,
        conflict_columns=["ticker", "fiscal_year", "fiscal_quarter"],
        update_columns=[
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
            "free_cash_flow",
            "net_cash_flow",
        ],
    ),
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
    match = PERIOD_PATTERN.match(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _fetch_html(url_template: str, ticker: str, label: str) -> str | None:
    html = None
    last_http_error: requests.HTTPError | None = None
    last_request_error: requests.RequestException | None = None
    tried_symbols = yahoo_quote_symbols(ticker)

    for yahoo_ticker in tried_symbols:
        try:
            html = get_text(url_template.format(ticker=yahoo_ticker), timeout=30)
            break
        except requests.HTTPError as exc:
            last_http_error = exc
            if exc.response is not None and exc.response.status_code in (404, 429):
                continue
            raise
        except requests.RequestException as exc:
            last_request_error = exc
            continue

    if html is not None:
        return html

    if last_http_error is not None and last_http_error.response is not None:
        status_code = last_http_error.response.status_code
        if status_code == 404:
            print(f"[warn] yahoo {label} not found for {ticker} (tried: {', '.join(tried_symbols)})")
            return None
        if status_code == 429:
            print(f"[warn] yahoo {label} rate limited for {ticker} (tried: {', '.join(tried_symbols)})")
            return None
    if last_request_error is not None:
        print(
            f"[warn] yahoo {label} request failed for {ticker} "
            f"(tried: {', '.join(tried_symbols)}): {last_request_error}"
        )
    return None


def _fetch_row_list_dataset(dataset: QuarterlyDataset, ticker: str) -> list[dict]:
    config = ROW_LIST_CONFIGS[dataset]
    html = _fetch_html(config.url, ticker, dataset.replace("_", " "))
    if html is None:
        return []

    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one(config.section_selector)
    if section is None:
        return []

    rows = []
    for row in section.select("div.table-body-wrapper ul > li"):
        period_text = None
        period_cell = row.select_one(config.period_cell_selector)
        if period_cell:
            period_text = period_cell.get_text(strip=True)

        values = [text for text in row.stripped_strings if text]
        if period_text and period_text in values:
            values.remove(period_text)
        if len(values) < config.min_values:
            continue

        period = _parse_period(period_text or "")
        if period is None:
            continue

        year, quarter = period
        row_data = {
            "ticker": ticker,
            "fiscal_year": year,
            "fiscal_quarter": quarter,
        }
        for index, field in enumerate(config.fields):
            row_data[field] = _parse_number(values[index])
        rows.append(row_data)
    return rows


def _extract_periods(section) -> list[tuple[int, int]]:
    periods: list[tuple[int, int]] = []
    header = section.select_one("div.table-header-wrapper")
    if not header:
        return periods

    for cell in header.select("div"):
        text = cell.get_text(strip=True)
        parsed = _parse_period(text)
        if parsed:
            periods.append(parsed)
    return periods


def _fetch_matrix_dataset(dataset: QuarterlyDataset, ticker: str) -> list[dict]:
    config = MATRIX_CONFIGS[dataset]
    html = _fetch_html(config.url, ticker, dataset.replace("_", " "))
    if html is None:
        return []

    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one(config.section_selector)
    if section is None:
        return []

    periods = _extract_periods(section)
    if not periods:
        return []

    data: dict[tuple[int, int], dict] = {
        period: {
            "ticker": ticker,
            "fiscal_year": period[0],
            "fiscal_quarter": period[1],
        }
        for period in periods
    }

    for row in section.select("div.table-body-wrapper ul > li"):
        label_cell = row.select_one(config.label_cell_selector)
        if not label_cell:
            continue
        label = label_cell.get_text(strip=True)
        field = config.label_map.get(label)
        if not field:
            continue
        values = [cell.get_text(strip=True) for cell in row.select(config.value_cell_selector)]
        for index, period in enumerate(periods):
            if index >= len(values):
                continue
            data[period][field] = _parse_number(values[index])

    return list(data.values())


def fetch_yahoo_quarterly(dataset: QuarterlyDataset, ticker: str) -> list[dict]:
    if dataset in ROW_LIST_CONFIGS:
        return _fetch_row_list_dataset(dataset, ticker)
    if dataset in MATRIX_CONFIGS:
        return _fetch_matrix_dataset(dataset, ticker)
    raise ValueError(f"unsupported dataset: {dataset}")


def upsert_yahoo_quarterly(db: Session, dataset: QuarterlyDataset, rows: Iterable[dict]) -> int:
    config = ROW_LIST_CONFIGS.get(dataset) or MATRIX_CONFIGS.get(dataset)
    if config is None:
        raise ValueError(f"unsupported dataset: {dataset}")

    count = 0
    for row in rows:
        stmt = (
            insert(config.model)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[
                    getattr(config.model, column)
                    for column in config.conflict_columns
                ],
                set_={
                    column: row.get(column)
                    for column in config.update_columns
                },
            )
        )
        db.execute(stmt)
        count += 1
    return count


def run_yahoo_quarterly_sync(dataset: QuarterlyDataset, ticker: str) -> int:
    from api.db import SessionLocal

    rows = fetch_yahoo_quarterly(dataset, ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_quarterly(db, dataset, rows)
        db.commit()
    return count


def run_yahoo_quarterly_batch(
    dataset: QuarterlyDataset,
    tickers: Iterable[str],
    commit_every: int = 20,
) -> int:
    from api.db import SessionLocal

    total = 0
    processed = 0
    with SessionLocal() as db:
        for ticker in tickers:
            rows = fetch_yahoo_quarterly(dataset, ticker)
            total += upsert_yahoo_quarterly(db, dataset, rows)
            processed += 1
            if processed % commit_every == 0:
                db.commit()
                print(f"{dataset}: processed {processed} tickers")
        db.commit()
    return total


def _comparison_columns(dataset: QuarterlyDataset) -> list[str]:
    config = ROW_LIST_CONFIGS.get(dataset) or MATRIX_CONFIGS.get(dataset)
    if config is None:
        raise ValueError(f"unsupported dataset: {dataset}")
    return ["fiscal_year", "fiscal_quarter", *config.update_columns]


def _db_top5(dataset: QuarterlyDataset, db: Session, ticker: str) -> list[tuple]:
    config = ROW_LIST_CONFIGS.get(dataset) or MATRIX_CONFIGS.get(dataset)
    if config is None:
        raise ValueError(f"unsupported dataset: {dataset}")

    columns = [getattr(config.model, column) for column in _comparison_columns(dataset)]
    rows = db.execute(
        select(*columns)
        .where(config.model.ticker == ticker)
        .order_by(config.model.fiscal_year.desc(), config.model.fiscal_quarter.desc())
        .limit(5)
    ).all()
    return [tuple(row) for row in rows]


def _normalize_top5_rows(dataset: QuarterlyDataset, rows: Iterable[dict]) -> list[tuple]:
    columns = _comparison_columns(dataset)
    normalized = []
    for row in rows:
        normalized.append(tuple(row.get(column) for column in columns))
    return normalized


def run_yahoo_quarterly_top5(
    dataset: QuarterlyDataset,
    tickers: Iterable[str],
    commit_every: int = 20,
) -> int:
    from api.db import SessionLocal

    total = 0
    processed = 0
    pending = 0
    with SessionLocal() as db:
        for ticker in tickers:
            rows = fetch_yahoo_quarterly(dataset, ticker)
            processed += 1
            top5 = rows[:5]
            if not top5:
                continue
            existing = _db_top5(dataset, db, ticker)
            incoming = _normalize_top5_rows(dataset, top5)
            if existing == incoming:
                continue
            total += upsert_yahoo_quarterly(db, dataset, top5)
            pending += 1
            if pending >= commit_every:
                db.commit()
                print(f"{dataset}: processed {processed} tickers")
                pending = 0
        db.commit()
    return total


def run_yahoo_quarterly_all(
    datasets: Iterable[QuarterlyDataset],
    tickers: Iterable[str],
    commit_every: int = 20,
    top5_only: bool = False,
) -> dict[str, int]:
    results: dict[str, int] = {}
    ticker_list = list(tickers)
    for dataset in datasets:
        mode = "top5" if top5_only else "full"
        print(f"starting {dataset} quarterly sync ({mode})...")
        if top5_only:
            inserted = run_yahoo_quarterly_top5(dataset, ticker_list, commit_every=commit_every)
        else:
            inserted = run_yahoo_quarterly_batch(dataset, ticker_list, commit_every=commit_every)
        results[dataset] = inserted
        print(f"finished {dataset}: inserted {inserted} rows")
    return results


def fetch_yahoo_eps(ticker: str) -> list[dict]:
    return fetch_yahoo_quarterly("eps", ticker)


def upsert_yahoo_eps(db: Session, rows: Iterable[dict]) -> int:
    return upsert_yahoo_quarterly(db, "eps", rows)


def run_yahoo_eps_sync(ticker: str) -> int:
    return run_yahoo_quarterly_sync("eps", ticker)


def fetch_yahoo_income_statement(ticker: str) -> list[dict]:
    return fetch_yahoo_quarterly("income_statement", ticker)


def upsert_yahoo_income_statement(db: Session, rows: Iterable[dict]) -> int:
    return upsert_yahoo_quarterly(db, "income_statement", rows)


def run_yahoo_income_sync(ticker: str) -> int:
    return run_yahoo_quarterly_sync("income_statement", ticker)


def fetch_yahoo_balance_sheet(ticker: str) -> list[dict]:
    return fetch_yahoo_quarterly("balance_sheet", ticker)


def upsert_yahoo_balance_sheet(db: Session, rows: Iterable[dict]) -> int:
    return upsert_yahoo_quarterly(db, "balance_sheet", rows)


def run_yahoo_balance_sync(ticker: str) -> int:
    return run_yahoo_quarterly_sync("balance_sheet", ticker)


def fetch_yahoo_cash_flow(ticker: str) -> list[dict]:
    return fetch_yahoo_quarterly("cash_flow", ticker)


def upsert_yahoo_cash_flow(db: Session, rows: Iterable[dict]) -> int:
    return upsert_yahoo_quarterly(db, "cash_flow", rows)


def run_yahoo_cash_flow_sync(ticker: str) -> int:
    return run_yahoo_quarterly_sync("cash_flow", ticker)


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified Yahoo quarterly ETL")
    parser.add_argument(
        "dataset",
        choices=["eps", "income_statement", "balance_sheet", "cash_flow", "all"],
        help="quarterly dataset to fetch",
    )
    parser.add_argument("ticker", nargs="?", help="stock ticker")
    parser.add_argument(
        "--all-tickers",
        action="store_true",
        help="run against all tickers from data/tickers/twstock_tickers.json",
    )
    parser.add_argument(
        "--top5",
        action="store_true",
        help="compare only the latest 5 rows per ticker before deciding whether to update",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=20,
        help="commit interval for batch mode",
    )
    args = parser.parse_args()

    if args.all_tickers:
        tickers = load_ticker_universe()
        if args.dataset == "all":
            results = run_yahoo_quarterly_all(
                ALL_QUARTERLY_DATASETS,
                tickers,
                commit_every=args.commit_every,
                top5_only=args.top5,
            )
            for dataset, inserted in results.items():
                print(f"{dataset} inserted={inserted}")
            return

        if args.top5:
            inserted = run_yahoo_quarterly_top5(
                args.dataset,
                tickers,
                commit_every=args.commit_every,
            )
        else:
            inserted = run_yahoo_quarterly_batch(
                args.dataset,
                tickers,
                commit_every=args.commit_every,
            )
        print(f"inserted {inserted} rows for {args.dataset} across {len(tickers)} tickers")
        return

    if args.dataset == "all":
        if not args.ticker:
            parser.error("dataset 'all' requires --all-tickers or a ticker")
        if args.top5:
            results = run_yahoo_quarterly_all(
                ALL_QUARTERLY_DATASETS,
                [args.ticker],
                commit_every=args.commit_every,
                top5_only=True,
            )
        else:
            results = {
                dataset: run_yahoo_quarterly_sync(dataset, args.ticker)
                for dataset in ALL_QUARTERLY_DATASETS
            }
        for dataset, inserted in results.items():
            print(f"{dataset} inserted={inserted} rows for {args.ticker}")
        return

    target = args.ticker or "2330"
    if args.top5:
        inserted = run_yahoo_quarterly_top5(
            args.dataset,
            [target],
            commit_every=args.commit_every,
        )
    else:
        inserted = run_yahoo_quarterly_sync(args.dataset, target)
    print(f"inserted {inserted} rows for {args.dataset} {target}")


if __name__ == "__main__":
    main()
