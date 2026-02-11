-- PostgreSQL schema for TW stock policy MVP
-- NOTE: Current active dataset: monthly_revenue (Yahoo). Quarterly financial tables retained for future use.

CREATE TABLE IF NOT EXISTS companies (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL UNIQUE,
  name TEXT NOT NULL,
  market TEXT,
  industry TEXT,
  source TEXT,
  raw_hash TEXT,
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financials_quarterly (
  id SERIAL PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  revenue NUMERIC,
  gross_profit NUMERIC,
  operating_income NUMERIC,
  net_income NUMERIC,
  total_assets NUMERIC,
  total_equity NUMERIC,
  share_capital NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (company_id, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS indicators_quarterly (
  id SERIAL PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  gross_margin NUMERIC,
  operating_margin NUMERIC,
  roi NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (company_id, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS etl_runs (
  id SERIAL PRIMARY KEY,
  endpoint TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  rows_fetched INTEGER,
  rows_upserted INTEGER,
  error TEXT
);

CREATE TABLE IF NOT EXISTS monthly_revenue (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  period DATE NOT NULL,
  month_revenue NUMERIC,
  month_mom_pct NUMERIC,
  month_prev_year_revenue NUMERIC,
  month_yoy_pct NUMERIC,
  cum_revenue NUMERIC,
  cum_prev_year_revenue NUMERIC,
  cum_yoy_pct NUMERIC,
  source TEXT NOT NULL DEFAULT 'yahoo',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, period)
);

CREATE TABLE IF NOT EXISTS eps_quarterly (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  eps NUMERIC,
  qoq_pct NUMERIC,
  yoy_pct NUMERIC,
  avg_price NUMERIC,
  source TEXT NOT NULL DEFAULT 'yahoo',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS income_statement_quarterly (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  revenue NUMERIC,
  gross_profit NUMERIC,
  operating_expense NUMERIC,
  operating_income NUMERIC,
  net_income NUMERIC,
  source TEXT NOT NULL DEFAULT 'yahoo',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS balance_sheet_quarterly (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  total_assets NUMERIC,
  total_liabilities NUMERIC,
  equity NUMERIC,
  current_assets NUMERIC,
  current_liabilities NUMERIC,
  source TEXT NOT NULL DEFAULT 'yahoo',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS cash_flow_quarterly (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  operating_cash_flow NUMERIC,
  investing_cash_flow NUMERIC,
  financing_cash_flow NUMERIC,
  free_cash_flow NUMERIC,
  net_cash_flow NUMERIC,
  source TEXT NOT NULL DEFAULT 'yahoo',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, fiscal_year, fiscal_quarter)
);
