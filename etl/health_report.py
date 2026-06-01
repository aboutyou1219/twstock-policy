from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Iterable, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import (
    BalanceSheetQuarter,
    CashFlowQuarter,
    EpsQuarter,
    EtlRun,
    IncomeStatementQuarter,
    MonthlyRevenue,
)
from etl.ticker_universe import load_ticker_universe


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    model: type
    period_columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    endpoint_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class LastRunSummary:
    endpoint: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    rows_fetched: int | None
    rows_upserted: int | None
    error: str | None


@dataclass(frozen=True)
class DatasetHealth:
    name: str
    rows: int
    universe_tickers: int
    covered_tickers: int
    missing_tickers: int
    missing_samples: list[str]
    latest_period: str | None
    target_period: str | None
    earliest_period: str | None
    stale_tickers: int
    stale_samples: list[str]
    key_null_rows: int
    latest_fetch: str | None
    period_distribution: list[tuple[str, int]]
    last_run: LastRunSummary


@dataclass(frozen=True)
class HealthReport:
    generated_at: str
    universe_tickers: int
    datasets: list[DatasetHealth]


DATASETS: tuple[DatasetConfig, ...] = (
    DatasetConfig(
        name="monthly_revenue",
        model=MonthlyRevenue,
        period_columns=("period",),
        key_columns=("month_revenue",),
        endpoint_prefixes=("yahoo_revenue_batch", "yahoo_revenue"),
    ),
    DatasetConfig(
        name="eps_quarterly",
        model=EpsQuarter,
        period_columns=("fiscal_year", "fiscal_quarter"),
        key_columns=("eps",),
        endpoint_prefixes=("yahoo_eps_batch", "yahoo_quarterly:eps", "eps"),
    ),
    DatasetConfig(
        name="income_statement_quarterly",
        model=IncomeStatementQuarter,
        period_columns=("fiscal_year", "fiscal_quarter"),
        key_columns=("revenue", "gross_profit", "operating_income", "net_income"),
        endpoint_prefixes=("yahoo_income_batch", "yahoo_quarterly:income_statement", "income_statement"),
    ),
    DatasetConfig(
        name="balance_sheet_quarterly",
        model=BalanceSheetQuarter,
        period_columns=("fiscal_year", "fiscal_quarter"),
        key_columns=("total_assets", "total_liabilities", "equity"),
        endpoint_prefixes=("yahoo_balance_batch", "yahoo_quarterly:balance_sheet", "balance_sheet"),
    ),
    DatasetConfig(
        name="cash_flow_quarterly",
        model=CashFlowQuarter,
        period_columns=("fiscal_year", "fiscal_quarter"),
        key_columns=("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"),
        endpoint_prefixes=("yahoo_cash_flow_batch", "yahoo_quarterly:cash_flow", "cash_flow"),
    ),
)


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _monthly_key(value) -> tuple[int, int]:
    if isinstance(value, datetime):
        return value.year, value.month
    if isinstance(value, date):
        return value.year, value.month
    raise ValueError(f"invalid monthly period: {value!r}")


def _quarter_key(year, quarter) -> tuple[int, int]:
    return int(year), int(quarter)


def _period_key(config: DatasetConfig, values: Sequence) -> tuple[int, int]:
    if len(config.period_columns) == 1:
        return _monthly_key(values[0])
    return _quarter_key(values[0], values[1])


def _period_label(config: DatasetConfig, key: tuple[int, int] | None) -> str | None:
    if key is None:
        return None
    if len(config.period_columns) == 1:
        return f"{key[0]:04d}-{key[1]:02d}"
    return f"{key[0]:04d}Q{key[1]}"


def _parse_month_target(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    year, month = value.split("-", 1)
    return int(year), int(month)


def _parse_quarter_target(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    normalized = value.upper().replace(" ", "")
    year, quarter = normalized.split("Q", 1)
    return int(year), int(quarter)


def _last_run(db: Session, prefixes: Iterable[str]) -> LastRunSummary:
    prefix_list = tuple(prefixes)
    rows = db.execute(
        select(EtlRun)
        .order_by(EtlRun.started_at.desc())
        .limit(200)
    ).scalars()
    for row in rows:
        if any(row.endpoint.startswith(prefix) for prefix in prefix_list):
            return LastRunSummary(
                endpoint=row.endpoint,
                status=row.status,
                started_at=_iso(row.started_at),
                finished_at=_iso(row.finished_at),
                rows_fetched=row.rows_fetched,
                rows_upserted=row.rows_upserted,
                error=row.error,
            )
    return LastRunSummary(None, None, None, None, None, None, None)


def _key_null_rows(db: Session, config: DatasetConfig) -> int:
    predicates = [getattr(config.model, column).is_(None) for column in config.key_columns]
    if not predicates:
        return 0
    return int(
        db.execute(
            select(func.count())
            .select_from(config.model)
            .where(or_(*predicates))
        ).scalar_one()
    )


def build_dataset_health(
    db: Session,
    config: DatasetConfig,
    tickers: Sequence[str],
    target_period: tuple[int, int] | None = None,
    sample_limit: int = 10,
) -> DatasetHealth:
    period_attrs = [getattr(config.model, column) for column in config.period_columns]
    rows = db.execute(
        select(config.model.ticker, *period_attrs, config.model.fetched_at)
    ).all()

    latest_by_ticker: dict[str, tuple[tuple[int, int], object | None]] = {}
    earliest_key: tuple[int, int] | None = None
    latest_key: tuple[int, int] | None = None
    latest_fetch = None

    for row in rows:
        ticker = str(row[0])
        key = _period_key(config, row[1:-1])
        fetched_at = row[-1]
        if earliest_key is None or key < earliest_key:
            earliest_key = key
        if latest_key is None or key > latest_key:
            latest_key = key
        if latest_fetch is None or (fetched_at is not None and fetched_at > latest_fetch):
            latest_fetch = fetched_at
        current = latest_by_ticker.get(ticker)
        if current is None or key > current[0]:
            latest_by_ticker[ticker] = (key, fetched_at)

    target_key = target_period or latest_key
    ticker_set = set(tickers)
    covered = ticker_set.intersection(latest_by_ticker)
    missing = sorted(ticker_set.difference(latest_by_ticker))
    stale = sorted(
        ticker
        for ticker in covered
        if target_key is not None and latest_by_ticker[ticker][0] < target_key
    )
    latest_period_counts = Counter(status[0] for status in latest_by_ticker.values())
    distribution = [
        (_period_label(config, key) or "", count)
        for key, count in latest_period_counts.most_common()
    ]
    distribution.sort(key=lambda item: item[0], reverse=True)

    return DatasetHealth(
        name=config.name,
        rows=len(rows),
        universe_tickers=len(tickers),
        covered_tickers=len(covered),
        missing_tickers=len(missing),
        missing_samples=missing[:sample_limit],
        latest_period=_period_label(config, latest_key),
        target_period=_period_label(config, target_key),
        earliest_period=_period_label(config, earliest_key),
        stale_tickers=len(stale),
        stale_samples=stale[:sample_limit],
        key_null_rows=_key_null_rows(db, config),
        latest_fetch=_iso(latest_fetch),
        period_distribution=distribution[:sample_limit],
        last_run=_last_run(db, config.endpoint_prefixes),
    )


def build_health_report(
    db: Session,
    tickers: Sequence[str],
    monthly_target: tuple[int, int] | None = None,
    quarterly_target: tuple[int, int] | None = None,
    sample_limit: int = 10,
) -> HealthReport:
    datasets: list[DatasetHealth] = []
    for config in DATASETS:
        target = monthly_target if config.name == "monthly_revenue" else quarterly_target
        datasets.append(
            build_dataset_health(
                db,
                config,
                tickers,
                target_period=target,
                sample_limit=sample_limit,
            )
        )
    return HealthReport(
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        universe_tickers=len(tickers),
        datasets=datasets,
    )


def _format_row(values: Sequence[object], widths: Sequence[int]) -> str:
    return "  ".join(str(value if value is not None else "-").ljust(width) for value, width in zip(values, widths))


def render_text(report: HealthReport) -> str:
    lines = [
        "TWStock ETL Health Report",
        f"generated_at={report.generated_at}",
        f"universe_tickers={report.universe_tickers}",
        "",
        "DATASET SUMMARY",
    ]
    headers = (
        "dataset",
        "rows",
        "covered",
        "missing",
        "latest",
        "target",
        "stale",
        "key_nulls",
        "latest_fetch",
        "last_run",
    )
    widths = (30, 8, 8, 8, 10, 10, 8, 10, 25, 16)
    lines.append(_format_row(headers, widths))
    lines.append(_format_row(tuple("-" * width for width in widths), widths))
    for dataset in report.datasets:
        last_run = dataset.last_run.status
        if dataset.last_run.endpoint:
            last_run = f"{dataset.last_run.status}:{dataset.last_run.endpoint}"
        lines.append(
            _format_row(
                (
                    dataset.name,
                    dataset.rows,
                    dataset.covered_tickers,
                    dataset.missing_tickers,
                    dataset.latest_period,
                    dataset.target_period,
                    dataset.stale_tickers,
                    dataset.key_null_rows,
                    dataset.latest_fetch,
                    last_run,
                ),
                widths,
            )
        )

    lines.append("")
    lines.append("GAPS")
    for dataset in report.datasets:
        if dataset.missing_tickers == 0 and dataset.stale_tickers == 0 and dataset.key_null_rows == 0:
            lines.append(f"{dataset.name}: OK")
            continue
        lines.append(
            f"{dataset.name}: missing={dataset.missing_tickers} "
            f"stale={dataset.stale_tickers} key_null_rows={dataset.key_null_rows}"
        )
        if dataset.missing_samples:
            lines.append(f"  missing_samples={', '.join(dataset.missing_samples)}")
        if dataset.stale_samples:
            lines.append(f"  stale_samples={', '.join(dataset.stale_samples)}")

    lines.append("")
    lines.append("LATEST PERIOD DISTRIBUTION")
    for dataset in report.datasets:
        parts = [f"{period}:{count}" for period, count in dataset.period_distribution]
        lines.append(f"{dataset.name}: {', '.join(parts) if parts else '-'}")

    return "\n".join(lines)


def report_to_json(report: HealthReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report ETL freshness and completeness from the database")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--monthly-target", help="expected monthly period, e.g. 2026-04")
    parser.add_argument("--quarterly-target", help="expected quarterly period, e.g. 2025Q4")
    args = parser.parse_args()

    tickers = load_ticker_universe()
    with SessionLocal() as db:
        report = build_health_report(
            db,
            tickers,
            monthly_target=_parse_month_target(args.monthly_target),
            quarterly_target=_parse_quarter_target(args.quarterly_target),
            sample_limit=args.sample_limit,
        )

    if args.format == "json":
        print(report_to_json(report))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main()
