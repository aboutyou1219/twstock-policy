from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.dialects import postgresql

from etl.daily_prices import upsert_daily_prices
from etl.technical_indicators import (
    calculate_indicators,
    upsert_daily_technical_indicators,
)
from etl.yahoo_quarterly import upsert_yahoo_quarterly
from etl.yahoo_revenue import upsert_yahoo_monthly_revenue


class FakeSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)


def _compiled_sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


class EtlUpsertTest(unittest.TestCase):
    def test_monthly_revenue_upsert_refreshes_fetched_at(self):
        db = FakeSession()

        inserted = upsert_yahoo_monthly_revenue(
            db,
            [
                {
                    "ticker": "2330",
                    "period": date(2026, 2, 1),
                    "month_revenue": 100,
                    "month_mom_pct": 1,
                    "month_prev_year_revenue": 90,
                    "month_yoy_pct": 11,
                    "cum_revenue": 100,
                    "cum_prev_year_revenue": 90,
                    "cum_yoy_pct": 11,
                }
            ],
        )

        self.assertEqual(inserted, 1)
        sql = _compiled_sql(db.statements[0])
        self.assertIn("fetched_at = now()", sql)
        self.assertIn("source = ", sql)

    def test_quarterly_upsert_refreshes_fetched_at(self):
        db = FakeSession()

        inserted = upsert_yahoo_quarterly(
            db,
            "income_statement",
            [
                {
                    "ticker": "2330",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "revenue": 100,
                    "gross_profit": 50,
                    "operating_expense": 10,
                    "operating_income": 40,
                    "net_income": 30,
                }
            ],
        )

        self.assertEqual(inserted, 1)
        sql = _compiled_sql(db.statements[0])
        self.assertIn("fetched_at = now()", sql)
        self.assertIn("source = ", sql)

    def test_daily_prices_upsert_refreshes_fetched_at(self):
        db = FakeSession()

        inserted = upsert_daily_prices(
            db,
            [
                {
                    "ticker": "2330",
                    "trade_date": date(2026, 6, 1),
                    "open_price": 100,
                    "high_price": 105,
                    "low_price": 99,
                    "close_price": 104,
                    "volume": 1000,
                    "turnover": 104000,
                    "transaction_count": 50,
                    "price_change": 4,
                    "source": "finmind",
                    "raw_payload": {"date": "2026-06-01"},
                }
            ],
        )

        self.assertEqual(inserted, 1)
        sql = _compiled_sql(db.statements[0])
        self.assertIn("fetched_at = now()", sql)
        self.assertIn("close_price = ", sql)

    def test_daily_technical_indicator_upsert_refreshes_fetched_at(self):
        db = FakeSession()

        inserted = upsert_daily_technical_indicators(
            db,
            [
                {
                    "ticker": "2330",
                    "trade_date": date(2026, 6, 1),
                    "ma5": 100,
                    "ma10": 99,
                    "ma20": 98,
                    "source": "derived",
                }
            ],
        )

        self.assertEqual(inserted, 1)
        sql = _compiled_sql(db.statements[0])
        self.assertIn("fetched_at = now()", sql)
        self.assertIn("ma5 = ", sql)

    def test_calculate_indicators_returns_expected_basic_values(self):
        start = date(2026, 1, 1)
        prices = pd.DataFrame(
            [
                {
                    "ticker": "2330",
                    "trade_date": start + timedelta(days=index),
                    "open_price": 100 + index,
                    "high_price": 101 + index,
                    "low_price": 99 + index,
                    "close_price": 100 + index,
                    "volume": 1000 + index,
                }
                for index in range(30)
            ]
        )

        rows = calculate_indicators(prices)

        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[-1]["ma5"], 127.0)
        self.assertEqual(rows[-1]["ma20"], 119.5)
        self.assertIsNotNone(rows[-1]["return_1d"])

    def test_calculate_indicators_converts_infinite_returns_to_none(self):
        start = date(2026, 1, 1)
        prices = pd.DataFrame(
            [
                {
                    "ticker": "6117",
                    "trade_date": start + timedelta(days=index),
                    "open_price": 10 if index != 10 else 0,
                    "high_price": 11 if index != 10 else 0,
                    "low_price": 9 if index != 10 else 0,
                    "close_price": 10 + index if index != 10 else 0,
                    "volume": 1000,
                }
                for index in range(30)
            ]
        )

        rows = calculate_indicators(prices)

        self.assertTrue(np.isinf(prices["close_price"].pct_change().iloc[11]))
        self.assertIsNone(rows[11]["return_1d"])


if __name__ == "__main__":
    unittest.main()
