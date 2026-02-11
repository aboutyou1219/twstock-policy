# twstock-policy
ETL（Yahoo 財務資料）專案

## 安裝

1. 建立並啟用虛擬環境

```bash
python3 -m venv .twstock
source .twstock/bin/activate
```

2. 安裝相依套件

專案根目錄已有 `requirement.txt`（請依需要更新）。

```bash
pip install -r requirement.txt
```

## 資料庫

建議使用 `yahoo_revenue` 資料庫：

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
```

建表：

```bash
psql "$DATABASE_URL" -f db/schema.sql
```

## 資料表一覽

- `monthly_revenue`：月營收（Yahoo 月營收表）
- `eps_quarterly`：EPS（Yahoo EPS 表）
- `income_statement_quarterly`：損益表（Yahoo 損益表）
- `balance_sheet_quarterly`：資產負債表（Yahoo 資產負債表）
- `cash_flow_quarterly`：現金流量表（Yahoo 現金流量表）

## Yahoo 月營收 ETL（單檔）

```bash
python -m etl.yahoo_revenue 2330
```

寫入資料表：`monthly_revenue`

## Yahoo EPS ETL（單檔）

```bash
python -m etl.yahoo_eps 6829
```

寫入資料表：`eps_quarterly`

## Yahoo 損益表 ETL（單檔）

```bash
python -m etl.yahoo_income_statement 6829
```

寫入資料表：`income_statement_quarterly`

## Yahoo 資產負債表 ETL（單檔）

```bash
python -m etl.yahoo_balance_sheet 6829
```

寫入資料表：`balance_sheet_quarterly`

## Yahoo 現金流量表 ETL（單檔）

```bash
python -m etl.yahoo_cash_flow 6829
```

寫入資料表：`cash_flow_quarterly`

## 推薦使用流程

1. 先跑單一 ticker 確認可寫入
2. 再跑批次 `--top5` 驗證比對/更新邏輯
3. 最後跑 `--all` 完整回補

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1

python -m etl.yahoo_revenue_batch --ticker 2337
python -m etl.yahoo_revenue_batch --top5
python -m etl.yahoo_revenue_batch --all
```

## Yahoo 月營收批次命令（主流程）

功能：
1. 批次爬蟲所有 Yahoo 月營收到 `yahoo_revenue` DB
2. 批次爬蟲所有 Yahoo 月營收前 5 筆資料，若與現有資料完全重複則跳過寫入

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1
python -m etl.yahoo_revenue_batch --all

python -m etl.yahoo_revenue_batch --top5

python -m etl.yahoo_revenue_batch --all --top5

python -m etl.yahoo_revenue_batch --ticker 2337
```

## Yahoo EPS 批次命令（主流程）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1
python -m etl.yahoo_eps_batch --all

python -m etl.yahoo_eps_batch --top5

python -m etl.yahoo_eps_batch --all --top5

python -m etl.yahoo_eps_batch --ticker 6829
```

## Yahoo 損益表批次命令（主流程）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1
python -m etl.yahoo_income_batch --all

python -m etl.yahoo_income_batch --top5

python -m etl.yahoo_income_batch --all --top5

python -m etl.yahoo_income_batch --ticker 6829
```

## Yahoo 資產負債表批次命令（主流程）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1
python -m etl.yahoo_balance_batch --all

python -m etl.yahoo_balance_batch --top5

python -m etl.yahoo_balance_batch --all --top5

python -m etl.yahoo_balance_batch --ticker 6829
```

## Yahoo 現金流量表批次命令（主流程）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/yahoo_revenue"
export ETL_QPS=1
python -m etl.yahoo_cash_flow_batch --all

python -m etl.yahoo_cash_flow_batch --top5

python -m etl.yahoo_cash_flow_batch --all --top5

python -m etl.yahoo_cash_flow_batch --ticker 6829
```

## ETL 更新策略（月度 + 季度）

月度資料（`monthly_revenue`）：
- 建議每日或每週跑 `--top5`（當月新資料會進來）。
- 每月初可跑一次 `--all` 做完整回補。

季度資料（EPS/損益/資產負債/現金流）：
- 建議每週跑 `--top5`（財報公布期密度高）。
- 每季結束後跑一次 `--all` 回補。

## ETL 優化建議

- **去重策略**：表已設 `UNIQUE (ticker, period)` 或 `(ticker, fiscal_year, fiscal_quarter)`，用 `upsert` 避免重複寫入。
- **效能**：建議保留 `--top5` 作為日常更新，`--all` 做低頻回補。
- **I/O 壓力**：已改為每 20 檔 commit 一次，可視需求調整。
- **失敗控管**：ETL 會寫入 `etl_runs`（記錄執行狀態與寫入筆數）。

## etl_runs 報表查詢

```sql
-- 最近 20 筆 ETL 執行紀錄
SELECT id, endpoint, status, started_at, finished_at, rows_fetched, rows_upserted, error
FROM etl_runs
ORDER BY started_at DESC
LIMIT 20;

-- 今日 ETL 成功/失敗數量
SELECT status, count(*) AS runs
FROM etl_runs
WHERE started_at::date = CURRENT_DATE
GROUP BY status
ORDER BY status;

-- 每個 endpoint 最近一次狀態
SELECT DISTINCT ON (endpoint)
  endpoint, status, started_at, rows_fetched, rows_upserted, error
FROM etl_runs
ORDER BY endpoint, started_at DESC;

-- 失敗明細（含 error）
SELECT id, endpoint, status, started_at, finished_at, error
FROM etl_runs
WHERE status <> 'success'
ORDER BY started_at DESC
LIMIT 50;

-- 平均耗時（秒），只看已完成的紀錄
SELECT endpoint,
       AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) AS avg_seconds,
       COUNT(*) AS runs
FROM etl_runs
WHERE finished_at IS NOT NULL
GROUP BY endpoint
ORDER BY avg_seconds DESC;
```

## 專案結構（目前用到）
- `etl/` Yahoo 財務爬蟲
- `db/` PostgreSQL schema
- `api/`, `web/` 目前未使用，可保留或後續移除
