from __future__ import annotations

import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.db import Base
from api.models import EpsQuarter, EtlRun, MonthlyRevenue
from etl.health_report import (
    DATASETS,
    build_dataset_health,
    build_health_report,
    render_text,
)


class EtlHealthReportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _config(self, name: str):
        return next(config for config in DATASETS if config.name == name)

    def test_dataset_health_flags_missing_stale_and_null_rows(self):
        fetched_at = datetime(2026, 3, 24, 12, 0, 0)
        self.db.add_all(
            [
                MonthlyRevenue(
                    ticker="1111",
                    period=date(2026, 2, 1),
                    month_revenue=100,
                    month_mom_pct=1,
                    month_prev_year_revenue=90,
                    month_yoy_pct=11,
                    cum_revenue=100,
                    cum_prev_year_revenue=90,
                    cum_yoy_pct=11,
                    source="test",
                    fetched_at=fetched_at,
                ),
                MonthlyRevenue(
                    ticker="2222",
                    period=date(2026, 1, 1),
                    month_revenue=None,
                    month_mom_pct=1,
                    month_prev_year_revenue=80,
                    month_yoy_pct=25,
                    cum_revenue=100,
                    cum_prev_year_revenue=80,
                    cum_yoy_pct=25,
                    source="test",
                    fetched_at=fetched_at,
                ),
                EtlRun(
                    endpoint="yahoo_revenue_batch",
                    status="success",
                    started_at=fetched_at,
                    finished_at=fetched_at,
                    rows_fetched=2,
                    rows_upserted=2,
                    error=None,
                ),
            ]
        )
        self.db.commit()

        health = build_dataset_health(
            self.db,
            self._config("monthly_revenue"),
            ["1111", "2222", "3333"],
            target_period=(2026, 2),
            sample_limit=5,
        )

        self.assertEqual(health.rows, 2)
        self.assertEqual(health.covered_tickers, 2)
        self.assertEqual(health.missing_tickers, 1)
        self.assertEqual(health.missing_samples, ["3333"])
        self.assertEqual(health.stale_tickers, 1)
        self.assertEqual(health.stale_samples, ["2222"])
        self.assertEqual(health.key_null_rows, 1)
        self.assertEqual(health.latest_period, "2026-02")
        self.assertEqual(health.period_distribution, [("2026-02", 1), ("2026-01", 1)])
        self.assertEqual(health.last_run.status, "success")

    def test_full_report_renders_dataset_summary(self):
        fetched_at = datetime(2026, 3, 24, 12, 0, 0)
        self.db.add(
            EpsQuarter(
                ticker="1111",
                fiscal_year=2025,
                fiscal_quarter=4,
                eps=3,
                qoq_pct=1,
                yoy_pct=2,
                avg_price=100,
                source="test",
                fetched_at=fetched_at,
            )
        )
        self.db.commit()

        report = build_health_report(
            self.db,
            ["1111", "2222"],
            quarterly_target=(2025, 4),
            sample_limit=3,
        )
        rendered = render_text(report)

        self.assertIn("DATASET SUMMARY", rendered)
        self.assertIn("eps_quarterly", rendered)
        self.assertIn("missing=1", rendered)
        eps_health = next(dataset for dataset in report.datasets if dataset.name == "eps_quarterly")
        self.assertEqual(eps_health.latest_period, "2025Q4")
        self.assertEqual(eps_health.missing_samples, ["2222"])


if __name__ == "__main__":
    unittest.main()
