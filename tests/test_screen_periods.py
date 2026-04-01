from __future__ import annotations

import unittest
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.db import Base
from api.main import app
from api.models import CompanyFinancialHighlight, CompanyProfile, EpsQuarter, IncomeStatementQuarter
from api.routes import get_db


class ScreenPeriodsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._seed_data()

    def _seed_data(self):
        db = self.SessionLocal()
        now = datetime(2026, 3, 31, 12, 0, 0)
        try:
            db.add_all(
                [
                    CompanyProfile(
                        ticker="1111",
                        company_name="Alpha",
                        market="上市",
                        industry="半導體業",
                        share_capital=500000000,
                        market_cap_million_twd=1000,
                        data_date=date(2026, 3, 31),
                        source="test",
                        fetched_at=now,
                    ),
                    CompanyProfile(
                        ticker="2222",
                        company_name="Beta",
                        market="上市",
                        industry="半導體業",
                        share_capital=600000000,
                        market_cap_million_twd=900,
                        data_date=date(2026, 3, 31),
                        source="test",
                        fetched_at=now,
                    ),
                    IncomeStatementQuarter(
                        ticker="1111",
                        fiscal_year=2025,
                        fiscal_quarter=4,
                        revenue=1000,
                        gross_profit=500,
                        operating_income=250,
                        net_income=200,
                        source="test",
                        fetched_at=now,
                    ),
                    IncomeStatementQuarter(
                        ticker="1111",
                        fiscal_year=2024,
                        fiscal_quarter=4,
                        revenue=1000,
                        gross_profit=400,
                        operating_income=200,
                        net_income=180,
                        source="test",
                        fetched_at=now,
                    ),
                    IncomeStatementQuarter(
                        ticker="2222",
                        fiscal_year=2025,
                        fiscal_quarter=4,
                        revenue=1000,
                        gross_profit=450,
                        operating_income=220,
                        net_income=180,
                        source="test",
                        fetched_at=now,
                    ),
                    IncomeStatementQuarter(
                        ticker="2222",
                        fiscal_year=2024,
                        fiscal_quarter=4,
                        revenue=1000,
                        gross_profit=400,
                        operating_income=180,
                        net_income=160,
                        source="test",
                        fetched_at=now,
                    ),
                    EpsQuarter(
                        ticker="1111",
                        fiscal_year=2025,
                        fiscal_quarter=4,
                        eps=3.0,
                        source="test",
                        fetched_at=now,
                    ),
                    EpsQuarter(
                        ticker="2222",
                        fiscal_year=2025,
                        fiscal_quarter=3,
                        eps=2.0,
                        source="test",
                        fetched_at=now,
                    ),
                    CompanyFinancialHighlight(
                        ticker="1111",
                        fiscal_year=2025,
                        fiscal_quarter=4,
                        gross_margin=50,
                        operating_margin=25,
                        roe=18,
                        roa=10,
                        book_value_per_share=20,
                        data_date=date(2026, 3, 31),
                        source="test",
                        fetched_at=now,
                    ),
                    CompanyFinancialHighlight(
                        ticker="2222",
                        fiscal_year=2025,
                        fiscal_quarter=3,
                        gross_margin=44,
                        operating_margin=20,
                        roe=16,
                        roa=9,
                        book_value_per_share=18,
                        data_date=date(2026, 3, 31),
                        source="test",
                        fetched_at=now,
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

    def test_latest_available_returns_metric_periods_and_non_stale(self):
        response = self.client.post("/api/v1/stocks/screen", json={})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        first = payload["items"][0]

        self.assertIn("gross_margin_period", first["metrics"])
        self.assertIn("roe_period", first["metrics"])
        self.assertIn("eps_period", first["metrics"])
        self.assertIn("resolved_period", first)
        self.assertIn("is_stale", first)
        self.assertFalse(first["is_stale"])

    def test_latest_available_preserves_existing_metric_filters(self):
        response = self.client.post(
            "/api/v1/stocks/screen",
            json={"min_eps": 2.5, "min_roe": 17},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual([item["ticker"] for item in payload["items"]], ["1111"])

    def test_fixed_period_requires_target_period(self):
        response = self.client.post(
            "/api/v1/stocks/screen",
            json={"period_mode": "fixed_period"},
        )
        self.assertEqual(response.status_code, 422)

    def test_fixed_period_rejects_invalid_quarter(self):
        response = self.client.post(
            "/api/v1/stocks/screen",
            json={
                "period_mode": "fixed_period",
                "target_fiscal_year": 2025,
                "target_fiscal_quarter": 5,
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "target_fiscal_quarter must be between 1 and 4")

    def test_fixed_period_exclude_stale_drops_inexact_rows(self):
        response = self.client.post(
            "/api/v1/stocks/screen",
            json={
                "period_mode": "fixed_period",
                "target_fiscal_year": 2025,
                "target_fiscal_quarter": 4,
                "stale_policy": "exclude_stale",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual([item["ticker"] for item in payload["items"]], ["1111"])
        self.assertFalse(payload["items"][0]["is_stale"])
        self.assertEqual(payload["items"][0]["resolved_period"], "2025Q4")

    def test_fixed_period_include_stale_falls_back_and_marks_item(self):
        response = self.client.post(
            "/api/v1/stocks/screen",
            json={
                "period_mode": "fixed_period",
                "target_fiscal_year": 2025,
                "target_fiscal_quarter": 4,
                "stale_policy": "include_stale_with_flag",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        items = {item["ticker"]: item for item in payload["items"]}

        self.assertIn("2222", items)
        self.assertTrue(items["2222"]["is_stale"])
        self.assertIsNone(items["2222"]["resolved_period"])
        self.assertEqual(items["2222"]["metrics"]["gross_margin_period"], "2025Q4")
        self.assertEqual(items["2222"]["metrics"]["eps_period"], "2025Q3")
        self.assertEqual(items["2222"]["metrics"]["roe_period"], "2025Q3")


if __name__ == "__main__":
    unittest.main()
