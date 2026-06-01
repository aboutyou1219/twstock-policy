from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy.dialects import postgresql

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


if __name__ == "__main__":
    unittest.main()
