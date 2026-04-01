# API README

此文件說明目前 API 端點與使用方式。API 以 FastAPI 提供服務，預設 base path 為 `/api`。

## 啟動

```bash
export DATABASE_URL="postgresql+psycopg://twstock:twstock@localhost:5432/twstock_fundamentals"
/home/victor/Documents/stock/.twstock/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## 健康檢查

`GET /health`

回傳：

```json
{"status":"ok"}
```

## 月營收查詢

`GET /api/monthly-revenue/{ticker}`

範例：

```
GET /api/monthly-revenue/2330
```

回傳：該股最新到最舊的月營收陣列。

## 核心篩選 (Screener)

`POST /api/v1/stocks/screen`

Request Body (JSON)：

```json
{
  "min_gross_margin": 30,
  "min_roi": 5,
  "min_revenue_yoy": 10,
  "max_share_capital": 10,
  "industry": "半導體業",
  "period_mode": "fixed_period",
  "target_fiscal_year": 2025,
  "target_fiscal_quarter": 4,
  "stale_policy": "include_stale_with_flag"
}
```

Query Params：
- `sort_by`: `gross_margin | operating_margin | revenue_yoy | eps | gross_margin_yoy_delta | roe | roa | cash_dividend`，預設 `gross_margin`
- `sort_dir`: `asc | desc`，預設 `desc`
- `limit`: 預設 `50`
- `offset`: 預設 `0`

回傳：

```json
{
  "count": 2,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "ticker": "2330",
      "name": "台積電",
      "industry": "半導體業",
      "latest_month": "2025-12-01",
      "latest_quarter": "2025 Q4",
      "resolved_period": "2025Q4",
      "is_stale": false,
      "metrics": {
        "gross_margin": 55.1,
        "gross_margin_period": "2025Q4",
        "roi": null,
        "roe": 18.2,
        "roe_period": "2025Q4",
        "operating_margin": 42.3,
        "eps": 14.2,
        "eps_period": "2025Q4",
        "revenue_yoy": 18.5,
        "share_capital_billion": 259.3
      }
    }
  ]
}
```

`period_mode`：
- `latest_available`：每個指標使用該公司目前最新可用期別
- `fixed_period`：優先使用指定 `target_fiscal_year` / `target_fiscal_quarter`

`stale_policy`：
- `exclude_stale`：指定期別缺資料就排除該股票
- `include_stale_with_flag`：回退到最近可用期別，並以 `is_stale=true` 標記

## 個股全方位診斷

`GET /api/v1/stocks/{ticker}/diagnostics`

範例：

```
GET /api/v1/stocks/2330/diagnostics
```

回傳結構：
- `basic`: 公司基本資訊（ticker/name/market/industry）
- `quarterly`: 四大季度資料（損益表/資產負債表/現金流量表/EPS）
- `monthly`: 近 24 個月營收趨勢

## 產業對比與排名

`GET /api/v1/industry/{industry_name}/rankings`

Query Params：
- `metric`: `gross_margin | operating_margin | roi`（預設 `operating_margin`）
- `limit`: 預設 `50`
- `offset`: 預設 `0`

範例：

```
GET /api/v1/industry/半導體業/rankings?metric=operating_margin
```

回傳：
- 產業平均值
- 排名結果（RANK）

## 系統監控與資料完整性

`GET /api/v1/system/status`

回傳：
- `last_success_at`: 最後一次成功同步時間
- `total_companies`: 公司總數
- `has_errors`: 最近 10 筆 ETL 是否有錯誤
- `recent_runs`: 最近 10 筆 ETL 紀錄
