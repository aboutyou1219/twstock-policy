# twstock-policy
ETL（Yahoo 財務資料）專案

目前主軸是把 Yahoo 的月營收與季度財報資料穩定寫進 PostgreSQL，供後續 API / 前端使用。

## 安裝

1. 建立並啟用虛擬環境

```bash
python3 -m venv .twstock
source .twstock/bin/activate
```

2. 安裝相依套件

專案根目錄已有 `requirement.txt`。

```bash
pip install -r requirement.txt
```

## 資料庫

建議使用 `twstock_fundamentals` 資料庫：

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
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
- `etl_runs`：批次 ETL 執行紀錄與統計

## 股票代號清單

ETL 不再自己在程式裡各自組股票代號名單，而是共用一份股票清單檔：

- 產生器：`etl/ticker_universe.py`
- 輸出檔案：`data/tickers/twstock_tickers.json`

這份 JSON 目前包含：

- `version`
- `generated_at`
- `source`
- `filters`
- `count`
- `tickers`

重建股票代號清單：

```bash
cd /home/victor/Documents/stock/twstock-policy
/home/victor/Documents/stock/.twstock/bin/python -m etl.ticker_universe
```

目前預設條件是：

- 只收 `twstock.codes` 裡的 `股票`
- 市場限 `上市`、`上櫃`
- 只收 4 位數數字代號

batch ETL 目前會優先讀 `data/tickers/twstock_tickers.json`；如果檔案不存在，才會 fallback 回即時產生名單。

## 目前可直接驗證的範圍

- 已可直接測試：五張 Yahoo 財務資料表的抓取與寫入
- 已可直接測試：`etl_runs` 的批次執行紀錄
- `api/` 與 `web/` 目前仍屬原型，若要一起驗證，請先確認對應資料表已有 ETL 寫入流程

## Yahoo 月營收 ETL（單檔）

```bash
python -m etl.yahoo_revenue 2330
```

寫入資料表：`monthly_revenue`

## Yahoo EPS ETL（單檔）

季度資料 ETL 已統一到 `etl.yahoo_quarterly`。目前保留：

- `etl.yahoo_eps`
- `etl.yahoo_income_statement`
- `etl.yahoo_balance_sheet`
- `etl.yahoo_cash_flow`

這四個模組作為相容 wrapper，所以舊指令仍可用；但新的統一入口建議改用 `etl.yahoo_quarterly`。

### 統一入口：單一資料集 / 單一股票

```bash
python -m etl.yahoo_quarterly eps 6829
python -m etl.yahoo_quarterly income_statement 6829
python -m etl.yahoo_quarterly balance_sheet 6829
python -m etl.yahoo_quarterly cash_flow 6829
```

### 統一入口：四種季度資料 / 單一股票

```bash
python -m etl.yahoo_quarterly all 6829
```

### 統一入口：`--top5` 日常更新模式

`etl.yahoo_quarterly` 已支援與舊 batch 相同的 `--top5` 比對模式：

- 先抓 Yahoo 最新資料
- 只取每檔最新 5 筆
- 與資料庫現有最新 5 筆逐欄比對
- 完全相同就跳過寫入
- 有差異才做 upsert

```bash
python -m etl.yahoo_quarterly eps 6829 --top5
python -m etl.yahoo_quarterly all 6829 --top5
```

### 統一入口：單一資料集 / 全部股票

```bash
python -m etl.yahoo_quarterly eps --all-tickers
python -m etl.yahoo_quarterly income_statement --all-tickers
python -m etl.yahoo_quarterly balance_sheet --all-tickers
python -m etl.yahoo_quarterly cash_flow --all-tickers
```

日常只更新最新季度時，建議直接加上 `--top5`：

```bash
python -m etl.yahoo_quarterly eps --all-tickers --top5
python -m etl.yahoo_quarterly income_statement --all-tickers --top5
python -m etl.yahoo_quarterly balance_sheet --all-tickers --top5
python -m etl.yahoo_quarterly cash_flow --all-tickers --top5
```

### 統一入口：四種季度資料 / 全部股票

這就是你要的「一次抓完所有季度財報資料」：

```bash
cd /home/victor/Documents/stock/twstock-policy
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

/home/victor/Documents/stock/.twstock/bin/python -m etl.ticker_universe
/home/victor/Documents/stock/.twstock/bin/python -m etl.yahoo_quarterly all --all-tickers
```

如果想調整 batch commit 頻率，可以加上：

```bash
/home/victor/Documents/stock/.twstock/bin/python -m etl.yahoo_quarterly all --all-tickers --commit-every 20
```

如果你是做季度例行更新，建議改跑：

```bash
/home/victor/Documents/stock/.twstock/bin/python -m etl.yahoo_quarterly all --all-tickers --top5
```

### 舊單檔 wrapper（相容保留）

如果你還有舊腳本依賴這些模組，仍可執行：

```bash
python -m etl.yahoo_eps 6829
python -m etl.yahoo_income_statement 6829
python -m etl.yahoo_balance_sheet 6829
python -m etl.yahoo_cash_flow 6829
```

寫入資料表：
- `eps_quarterly`
- `income_statement_quarterly`
- `balance_sheet_quarterly`
- `cash_flow_quarterly`

## 推薦使用流程

1. 先跑單一 ticker，確認 parser 與 DB 寫入正常
2. 再跑批次 `--top5`，驗證最近資料比對後才更新的邏輯
3. 最後跑批次 `--all`，做完整回補

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_revenue_batch --ticker 2337
python -m etl.yahoo_revenue_batch --top5
python -m etl.yahoo_revenue_batch --all
```

## 批次命令行為說明

五支 batch 指令目前都遵循同一套規則：

- `--ticker <代號>`：只跑單一股票，適合先做小範圍驗證
- `--top5`：掃描所有股票，但只比對 / 更新最新 5 筆資料
- `--all`：掃描所有股票並完整回補全部可抓到的資料
- `--all --top5`：先完整回補，再做一次 top5 比對更新

除了 `--ticker` 以外，batch ETL 會以 `data/tickers/twstock_tickers.json` 的 `tickers` 清單作為股票來源。

批次腳本執行完會輸出：

- `tickers_processed`
- `rows_fetched`
- `rows_inserted`
- `top5_updated`
- `top5_skipped`
- `errors`

同時也會寫入 `etl_runs`，方便後續查詢最近一次批次狀態。

## Yahoo 月營收批次命令（主流程）

功能：
1. `--all`：批次爬蟲所有 Yahoo 月營收並寫入 DB
2. `--top5`：只比對每檔最新 5 筆，若與現有資料完全相同則跳過寫入

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_revenue_batch --ticker 2337

python -m etl.yahoo_revenue_batch --top5

python -m etl.yahoo_revenue_batch --all

python -m etl.yahoo_revenue_batch --all --top5
```

## 舊季度 Batch 入口（相容保留）

以下 `*_batch.py` 仍可執行，但之後建議都改用 `etl.yahoo_quarterly`。它們保留的目的主要是相容舊流程與舊腳本。

## Yahoo EPS 批次命令（舊入口）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_eps_batch --ticker 6829

python -m etl.yahoo_eps_batch --top5

python -m etl.yahoo_eps_batch --all

python -m etl.yahoo_eps_batch --all --top5
```

## Yahoo 損益表批次命令（舊入口）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_income_batch --ticker 6829

python -m etl.yahoo_income_batch --top5

python -m etl.yahoo_income_batch --all

python -m etl.yahoo_income_batch --all --top5
```

## Yahoo 資產負債表批次命令（舊入口）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_balance_batch --ticker 6829

python -m etl.yahoo_balance_batch --top5

python -m etl.yahoo_balance_batch --all

python -m etl.yahoo_balance_batch --all --top5
```

## Yahoo 現金流量表批次命令（舊入口）

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.yahoo_cash_flow_batch --ticker 6829

python -m etl.yahoo_cash_flow_batch --top5

python -m etl.yahoo_cash_flow_batch --all

python -m etl.yahoo_cash_flow_batch --all --top5
```

## ETL 更新策略（月度 + 季度）

月度資料（`monthly_revenue`）：
- 建議每日或每週跑 `--top5`（當月新資料會進來）。
- 每月初可跑一次 `--all` 做完整回補。

季度資料（EPS/損益/資產負債/現金流）：
- 之後統一使用 `python -m etl.yahoo_quarterly ...`
- 建議每週跑 `python -m etl.yahoo_quarterly all --all-tickers --top5`
- 每季結束後跑一次 `python -m etl.yahoo_quarterly all --all-tickers` 回補。

## ETL 優化建議

- **去重策略**：表已設 `UNIQUE (ticker, period)` 或 `(ticker, fiscal_year, fiscal_quarter)`，用 `upsert` 避免重複寫入。
- **效能**：建議保留 `--top5` 作為日常更新，`--all` 做低頻回補。
- **I/O 壓力**：批次流程目前每 20 檔 commit 一次，可視需求調整。
- **失敗控管**：ETL 會寫入 `etl_runs`（記錄執行狀態與寫入筆數）。

## 建議測試腳本

如果你要依 README 逐步驗證，建議先跑這組：

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
export ETL_QPS=1

python -m etl.ticker_universe

python -m etl.yahoo_revenue 2330
python -m etl.yahoo_revenue_batch --ticker 2330
python -m etl.yahoo_revenue_batch --top5

python -m etl.yahoo_quarterly all 2330
python -m etl.yahoo_quarterly all 2330 --top5
python -m etl.yahoo_quarterly all --all-tickers --top5
```

驗證重點：

- `python -m etl.ticker_universe` 會生成或更新 `data/tickers/twstock_tickers.json`
- 單檔 ETL 能正常寫入資料表
- `etl.yahoo_quarterly ... --top5` 會先比對最新 5 筆，只有資料變動才更新
- `etl.yahoo_quarterly all --all-tickers --top5` 可作為季度日常主流程
- 同樣指令重跑時，不應產生明顯重複資料

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

## 專案結構（目前）
- `etl/`：Yahoo 財務爬蟲與批次流程
- `db/`：PostgreSQL schema
- `api/`：FastAPI 原型
- `web/`：Next.js 原型前端
