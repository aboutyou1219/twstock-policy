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

CREATE TABLE IF NOT EXISTS company_profiles (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  yahoo_symbol VARCHAR(20),
  company_name TEXT NOT NULL,
  english_short_name TEXT,
  market TEXT,
  industry TEXT,
  spokesperson TEXT,
  acting_spokesperson TEXT,
  chairman TEXT,
  general_manager TEXT,
  phone TEXT,
  fax TEXT,
  email TEXT,
  website TEXT,
  address TEXT,
  stock_transfer_agent TEXT,
  auditor TEXT,
  group_name TEXT,
  business_summary TEXT,
  established_date DATE,
  listed_date DATE,
  share_capital NUMERIC(20, 2),
  issued_common_shares BIGINT,
  market_cap_million_twd NUMERIC(20, 4),
  director_supervisor_holding_pct NUMERIC(8, 4),
  data_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'yahoo',
  source_url TEXT,
  raw_payload JSONB,
  raw_hash TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, data_date, source)
);

CREATE INDEX IF NOT EXISTS idx_company_profiles_ticker
  ON company_profiles (ticker);

CREATE INDEX IF NOT EXISTS idx_company_profiles_ticker_data_date
  ON company_profiles (ticker, data_date DESC);

CREATE TABLE IF NOT EXISTS company_dividend_summaries (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  dividend_year INTEGER,
  cash_dividend NUMERIC(20, 4),
  earnings_stock_dividend NUMERIC(20, 4),
  capital_reserve_stock_dividend NUMERIC(20, 4),
  stock_dividend NUMERIC(20, 4),
  is_advance_notice BOOLEAN NOT NULL DEFAULT FALSE,
  data_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'yahoo',
  source_url TEXT,
  raw_payload JSONB,
  raw_hash TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, data_date, source)
);

CREATE INDEX IF NOT EXISTS idx_company_dividend_summaries_ticker_data_date
  ON company_dividend_summaries (ticker, data_date DESC);

CREATE TABLE IF NOT EXISTS company_financial_highlights (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
  gross_margin NUMERIC(10, 4),
  operating_margin NUMERIC(10, 4),
  roa NUMERIC(10, 4),
  roe NUMERIC(10, 4),
  pretax_margin NUMERIC(10, 4),
  book_value_per_share NUMERIC(20, 4),
  data_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'yahoo',
  source_url TEXT,
  raw_payload JSONB,
  raw_hash TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, fiscal_year, fiscal_quarter, data_date, source)
);

CREATE INDEX IF NOT EXISTS idx_company_financial_highlights_ticker_period
  ON company_financial_highlights (ticker, fiscal_year DESC, fiscal_quarter DESC, data_date DESC);

CREATE TABLE IF NOT EXISTS company_financial_highlight_eps (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  series_type TEXT NOT NULL CHECK (series_type IN ('quarterly_eps', 'annual_eps')),
  period_label TEXT NOT NULL,
  fiscal_year INTEGER NOT NULL,
  fiscal_quarter INTEGER CHECK (fiscal_quarter BETWEEN 1 AND 4),
  eps NUMERIC(20, 4),
  display_order INTEGER NOT NULL DEFAULT 0,
  data_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'yahoo',
  source_url TEXT,
  raw_hash TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, series_type, period_label, data_date, source)
);

CREATE INDEX IF NOT EXISTS idx_company_financial_highlight_eps_ticker_series
  ON company_financial_highlight_eps (ticker, series_type, display_order, data_date DESC);

CREATE TABLE IF NOT EXISTS company_calendar_events (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  section_key TEXT NOT NULL,
  event_name TEXT NOT NULL,
  event_date DATE,
  event_end_date DATE,
  event_value_text TEXT,
  data_date DATE NOT NULL,
  source TEXT NOT NULL DEFAULT 'yahoo',
  source_url TEXT,
  raw_payload JSONB,
  raw_hash TEXT,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, section_key, event_name, data_date, source)
);

CREATE INDEX IF NOT EXISTS idx_company_calendar_events_ticker_data_date
  ON company_calendar_events (ticker, data_date DESC, section_key);

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

CREATE TABLE IF NOT EXISTS daily_prices (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  trade_date DATE NOT NULL,
  open_price NUMERIC(20, 4),
  high_price NUMERIC(20, 4),
  low_price NUMERIC(20, 4),
  close_price NUMERIC(20, 4),
  volume BIGINT,
  turnover NUMERIC(24, 4),
  transaction_count BIGINT,
  price_change NUMERIC(20, 4),
  market TEXT,
  source TEXT NOT NULL DEFAULT 'finmind',
  raw_payload JSONB,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_trade_date
  ON daily_prices (ticker, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_prices_trade_date
  ON daily_prices (trade_date DESC);

CREATE TABLE IF NOT EXISTS daily_technical_indicators (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  trade_date DATE NOT NULL,
  ma5 NUMERIC(20, 4),
  ma10 NUMERIC(20, 4),
  ma20 NUMERIC(20, 4),
  ma60 NUMERIC(20, 4),
  ma120 NUMERIC(20, 4),
  ma240 NUMERIC(20, 4),
  volume_ma5 NUMERIC(24, 4),
  volume_ma20 NUMERIC(24, 4),
  rsi14 NUMERIC(10, 4),
  macd_dif NUMERIC(20, 4),
  macd_dea NUMERIC(20, 4),
  macd_hist NUMERIC(20, 4),
  k9 NUMERIC(10, 4),
  d9 NUMERIC(10, 4),
  bb_mid NUMERIC(20, 4),
  bb_upper NUMERIC(20, 4),
  bb_lower NUMERIC(20, 4),
  return_1d NUMERIC(12, 4),
  return_5d NUMERIC(12, 4),
  return_20d NUMERIC(12, 4),
  return_60d NUMERIC(12, 4),
  high_52w NUMERIC(20, 4),
  low_52w NUMERIC(20, 4),
  source TEXT NOT NULL DEFAULT 'derived',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_technical_indicators_ticker_trade_date
  ON daily_technical_indicators (ticker, trade_date DESC);

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
