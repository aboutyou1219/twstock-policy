# Screener UI PRD

## 1. Product Summary

產品定位：把台股財報與營運資料，轉成可重複執行的策略篩選器。

核心任務：讓使用者用接近選股語言的方式，快速找出符合條件的股票，並立即理解入選原因。

不是什麼：

- 不是通用財報入口網站
- 不是首頁導覽型 dashboard
- 不是先看圖再猜結論的 BI 工具

## 2. Aligned Decisions

以下決策已確認，可作為工程開發基準：

- `比去年毛利高 5%` 的正式定義：`毛利率較去年同季增加 5 個百分點`
- `ROI` 公式與資料來源：待議，可能由 Yahoo financial 頁面直接抓取；MVP 不將 ROI 作為 blocking 指標
- MVP 條件模式：只做 `全部符合`
- 結果列表預設排序：`符合策略程度`

## 3. Target User

主要使用者：

- 有固定選股邏輯的主動投資者
- 會使用 `毛利率 > 30%`、`EPS > 2`、`股本 < 10 億` 這類條件的人
- 想快速掃市場、縮小名單、再做深度研究的人

次要使用者：

- 想從產業角度找優質公司的人
- 想檢查單一股票近期體質變化的人

## 4. User Problems

- 條件分散在不同資料表與頁面，難以一次判斷
- 月資料與季資料混在一起，容易誤判時間基準
- 找到股票後，還要跳到別處驗證原因
- 常用策略無法保存或重複套用

## 5. Product Goals

MVP 目標：

- 30 秒內建立一組條件
- 5 秒內取得結果列表
- 10 秒內看懂每檔股票為何入選
- 明確知道每個指標對應的資料時間

## 6. Core Use Cases

1. 找出 `毛利高、EPS 達標、股本小` 的公司
2. 找出 `毛利率較去年同季改善` 的公司
3. 先用模板篩一輪，再微調條件
4. 從結果直接進到個股詳情確認趨勢

## 7. MVP Scope

必做：

- 策略篩選首頁
- 條件 builder
- 預設策略模板
- 結果列表
- 個股診斷頁入口
- 產業篩選
- 排序與分頁
- 資料時間標示
- 缺資料狀態提示

不在 MVP：

- 回測
- 自訂公式
- 通知
- 多策略比較
- 進階 AND/OR 群組
- 多頁籤工作區

## 8. Information Architecture

主要頁面：

- `/screener`：策略篩選工作台
- `/stocks/[ticker]`：個股診斷頁
- `/industries/[industry]`：產業排名頁
- `/saved-screens`：已儲存策略
- `/system`：資料與 ETL 狀態

## 9. Wireframe Structure

### 9.1 Screener 首頁

```text
+----------------------------------------------------------------------------------+
| Header                                                                           |
| Logo | Screener | Industries | Saved Screens | System Status                     |
+----------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------+
| Hero / Quick Start                                                               |
| 標題：用策略語言找股票                                                           |
| 說明：依毛利率、營益率、EPS、股本與 YoY 變化快速篩選                             |
| [模板1 高毛利成長] [模板2 小股本高獲利] [模板3 毛利率改善]                        |
| 資料時間：月營收最新 YYYY-MM，季資料最新 YYYY Qn                                  |
+----------------------------------------------------------------------------------+

+----------------------------------+-----------------------------------------------+
| 左側：條件設定區                  | 右側：結果區                                  |
|----------------------------------|-----------------------------------------------|
| 篩選條件                         | 結果摘要                                      |
| [新增條件 +]                     | 共 42 檔，依符合策略程度排序                   |
|                                  |                                               |
| 條件卡 1                         | 排序：[符合策略程度 v]                         |
| 指標：[毛利率 v]                 | -------------------------------------------   |
| 比較：[>= v]                     | 2330 台積電  半導體                           |
| 數值：[30] [%]                   | 毛利率 55.1 | 營益率 42.3 | EPS 12.3          |
| 基準：[最新季 v]                 | 股本 259.3 億 | 毛利率年增 +6.2 百分點       |
|                                  | 命中：毛利率 >= 30, EPS > 2...                |
| 條件卡 2                         | [看診斷]                                      |
| 指標：[EPS v]                    | -------------------------------------------   |
| 比較：[>]                        | ...                                           |
| 數值：[2] [元]                   |                                               |
| 基準：[最新季 v]                 |                                               |
|                                  |                                               |
| 條件卡 3                         |                                               |
| 指標：[股本 v]                   |                                               |
| 比較：[<=]                       |                                               |
| 數值：[10] [億]                  |                                               |
| 基準：[最新季 v]                 |                                               |
|                                  |                                               |
| 條件卡 4                         |                                               |
| 指標：[毛利率較去年同季變化 v]   |                                               |
| 比較：[>=]                       |                                               |
| 數值：[5] [百分點]               |                                               |
| 基準：[最新季 vs 去年同季 v]     |                                               |
|                                  |                                               |
| 進階設定                         |                                               |
| 產業：[全部產業 v]               |                                               |
| 條件模式：[全部符合]             |                                               |
|                                  |                                               |
| [開始篩選] [清除條件] [儲存策略]  |                                               |
+----------------------------------+-----------------------------------------------+
```

### 9.2 個股診斷頁

```text
+----------------------------------------------------------------------------------+
| 基本資訊：2330 台積電 | 半導體業 | 上市                                           |
+----------------------------------------------------------------------------------+

+-------------------------------+-------------------------------+------------------+
| 關鍵指標摘要                  | 策略命中摘要                  | 產業排名          |
| 毛利率 / 營益率 / EPS         | 符合哪些條件、不符合哪些條件   | 毛利率第 x 名      |
+-------------------------------+-------------------------------+------------------+

+----------------------------------------------------------------------------------+
| 趨勢圖區                                                                     |
| [近 8 季] 毛利率 / 營益率 / EPS                                               |
| [近 24 月] 月營收 YoY                                                         |
+----------------------------------------------------------------------------------+
```

## 10. Frontend Component Tree

```text
app/
  screener/
    page.tsx
  stocks/
    [ticker]/
      page.tsx

components/
  screener/
    ScreenerWorkbench.tsx
    ScreenerHeader.tsx
    DataFreshnessBanner.tsx
    PresetStrategyChips.tsx
    RuleBuilder.tsx
    RuleCard.tsx
    ResultsPanel.tsx
    ResultsToolbar.tsx
    ResultsSummary.tsx
    StockResultsTable.tsx
    StockResultRow.tsx
    MatchScoreBadge.tsx
    MatchedRulesList.tsx
    EmptyState.tsx
    ErrorState.tsx
    LoadingState.tsx
```

MVP 必做元件：

- `ScreenerWorkbench`
- `DataFreshnessBanner`
- `PresetStrategyChips`
- `RuleBuilder`
- `RuleCard`
- `ResultsPanel`
- `ResultsToolbar`
- `StockResultsTable`
- `MatchedRulesList`
- `EmptyState`
- `LoadingState`

## 11. Frontend State Model

```ts
export type MetricKey =
  | "gross_margin"
  | "operating_margin"
  | "eps"
  | "share_capital"
  | "revenue_yoy"
  | "gross_margin_yoy_delta";

export type Operator = ">=" | ">" | "<=" | "<" | "=";

export type PeriodKey =
  | "latest_quarter"
  | "latest_month"
  | "latest_vs_last_year_same_quarter";

export type Rule = {
  id: string;
  metric: MetricKey;
  operator: Operator;
  value: number;
  unit?: "%" | "億" | "元" | "百分點";
  period: PeriodKey;
};
```

## 12. API Contract Draft

### 12.1 Metadata

`GET /api/v1/screens/metadata`

用途：

- 提供可用指標清單
- 提供產業清單
- 回傳資料時間
- 指定預設排序與可用條件模式

Response 範例：

```json
{
  "match_mode": ["all"],
  "default_sort": {
    "by": "match_score",
    "dir": "desc"
  },
  "metrics": [
    {
      "key": "gross_margin",
      "label": "毛利率",
      "unit": "%",
      "periods": ["latest_quarter"]
    },
    {
      "key": "eps",
      "label": "EPS",
      "unit": "元",
      "periods": ["latest_quarter"]
    },
    {
      "key": "gross_margin_yoy_delta",
      "label": "毛利率較去年同季變化",
      "unit": "百分點",
      "periods": ["latest_vs_last_year_same_quarter"]
    }
  ],
  "notes": {
    "gross_margin_yoy_delta": "最新季毛利率減去年同季毛利率",
    "roi": "MVP 暫不開放，待公式確認"
  }
}
```

### 12.2 Screen Query

`POST /api/v1/screens/query`

Request 範例：

```json
{
  "rules": [
    {
      "metric": "gross_margin",
      "operator": ">=",
      "value": 30,
      "unit": "%",
      "period": "latest_quarter"
    },
    {
      "metric": "eps",
      "operator": ">",
      "value": 2,
      "unit": "元",
      "period": "latest_quarter"
    },
    {
      "metric": "share_capital",
      "operator": "<=",
      "value": 10,
      "unit": "億",
      "period": "latest_quarter"
    },
    {
      "metric": "gross_margin_yoy_delta",
      "operator": ">=",
      "value": 5,
      "unit": "百分點",
      "period": "latest_vs_last_year_same_quarter"
    }
  ],
  "industry": "半導體業",
  "sort": {
    "by": "match_score",
    "dir": "desc"
  },
  "page": 1,
  "page_size": 50
}
```

## 13. Company Profile Integration Review

### 13.1 Current Data Inventory

`company_profiles` 已可提供以下類型的資料：

- 公司識別：`ticker`、`company_name`、`english_short_name`、`market`、`industry`
- 經營團隊：`chairman`、`general_manager`、`spokesperson`、`acting_spokesperson`
- 聯絡資訊：`website`、`phone`、`fax`、`email`、`address`
- 股務與簽證：`stock_transfer_agent`、`auditor`
- 公司背景：`group_name`、`business_summary`、`established_date`、`listed_date`
- 規模與治理：`share_capital`、`issued_common_shares`、`market_cap_million_twd`、`director_supervisor_holding_pct`
- 快照控制：`data_date`、`source_url`、`raw_payload`、`raw_hash`

### 13.2 Design Consultation Summary

`company_profiles` 的價值在於「幫使用者確認這家公司是誰」，不是「作為篩選主因子」。

因此設計上不建議把這批欄位直接展開在 screener 主表，原因如下：

- Screener 主頁的核心任務是快速收斂名單，不是閱讀公司百科
- 若把董事長、網站、成立時間、股務代理塞進結果表，會破壞掃描效率
- 這些欄位更適合放在個股的認識層與驗證層，而不是排序層

### 13.3 Layout Recommendation

#### A. Screener 結果列表

只放對「快速辨識」有幫助的 company profile 欄位：

- `company_name`
- `market`
- `industry`
- `group_name`：可選，建議先做成次要 badge，而不是表格欄位
- `market_cap_million_twd`：不建議先放主表，除非之後真的要當排序欄位

設計建議：

- 在結果卡標題區保留 `ticker + company_name`
- `market` 與 `industry` 以 badge 呈現
- `group_name` 若存在，可做成灰階次要 tag
- `data_date` 不必每卡都顯示，統一放在結果頁資料時間區即可

#### B. Screener 結果卡展開 / 側邊抽屜

這層是最適合導入 `company_profiles` 的地方，作為「快速認識公司」模組。

建議內容：

- 公司英文簡稱
- 董事長 / 總經理 / 發言人
- 公司網站
- 所屬集團
- 成立時間 / 掛牌日期
- 股本 / 已發行普通股數
- 市值（百萬）
- 董監持股比例
- 主要經營業務摘要

設計原則：

- 以 2 欄資訊格呈現，不做長表格
- `business_summary` 單獨一個全文區塊
- 對外連結只保留 `website`

#### C. 個股詳情頁 `/stocks/[ticker]`

這頁應該把 `company_profiles` 做成固定的「公司基本資料」區塊，位置放在財務趨勢與策略命中摘要之上。

建議結構：

1. 頁首基本識別
- `ticker`
- `company_name`
- `english_short_name`
- `market`
- `industry`
- `group_name`

2. 公司概況卡
- `chairman`
- `general_manager`
- `spokesperson`
- `website`
- `established_date`
- `listed_date`

3. 公司規模與治理卡
- `share_capital`
- `issued_common_shares`
- `market_cap_million_twd`
- `director_supervisor_holding_pct`
- `stock_transfer_agent`
- `auditor`

4. 業務簡介
- `business_summary`

### 13.4 MVP Decision

MVP 建議分兩階段導入：

Phase 1
- Screener 結果卡加入 `market` badge
- 個股詳情頁新增 `company profile summary`

Phase 2
- Screener 結果卡支援 `group_name` tag
- 結果卡或抽屜顯示 `website / chairman / market_cap_million_twd`

不建議在 MVP 直接做：

- 把 `company_profiles` 欄位塞進結果 table 多欄位
- 把聯絡資訊與股務資訊放進主結果列表
- 把 `raw_payload` 暴露到前端

## 14. Plan-Eng-Review Handoff

### 14.1 Architecture Decision

前端應將 `company_profiles` 視為「company identity layer」，與 screener metric layer 分開。

建議資料流：

- `screen` API：回傳篩選必要欄位 + 精簡 profile 欄位
- `profile` API：回傳單一股票最新 `company_profiles` 快照
- `diagnostics` API：之後可選擇合併 profile summary，或由前端平行請求

### 14.2 API Requirements

#### Option A. Extend screen response

在 `/api/v1/stocks/screen` 每個 item 補：

```json
{
  "profile": {
    "market": "上市",
    "group_name": "台積電集團",
    "market_cap_million_twd": 123456.78
  }
}
```

這版只建議帶非常輕量的欄位。

#### Option B. Add profile endpoint

新增：

`GET /api/v1/stocks/{ticker}/profile`

Response 範例：

```json
{
  "ticker": "2330",
  "company_name": "台積電",
  "english_short_name": "TSMC",
  "market": "上市",
  "industry": "半導體業",
  "group_name": "台積電集團",
  "chairman": "...",
  "general_manager": "...",
  "spokesperson": "...",
  "website": "https://...",
  "established_date": "1987-02-21",
  "listed_date": "1994-09-05",
  "share_capital": 259303800000,
  "issued_common_shares": 25930380000,
  "market_cap_million_twd": 12345678.12,
  "director_supervisor_holding_pct": 6.23,
  "stock_transfer_agent": "...",
  "auditor": "...",
  "business_summary": "...",
  "data_date": "2026-03-24"
}
```

工程上建議優先採用 Option B，理由是：

- screener 主 query 不需要為了 profile 欄位變重
- 前端可以按需載入，不會拖慢結果頁
- profile schema 後續擴充更容易

### 14.3 Frontend Component Additions

建議新增：

```text
components/
  screener/
    CompanyIdentityBadges.tsx
    CompanyProfilePreview.tsx

  stock/
    CompanyProfileSummary.tsx
    CompanyGovernanceCard.tsx
    CompanyBusinessSummary.tsx
```

### 14.4 Page Composition Update

#### Screener 結果卡

- 保留財務指標為主
- 新增 `market` badge
- 預留 `group_name` tag 插槽
- `查看診斷` 進入個股詳情頁

#### Stock 詳情頁

頁面結構應更新為：

```text
Stock Header
Company Profile Summary
Governance / Scale Cards
Strategy Hit Reasons
Quarterly Trend Section
Monthly Revenue Section
Financial Tabs
```

### 14.5 Development Sequence

1. 新增 `GET /api/v1/stocks/{ticker}/profile`
2. 以最新 `data_date` 取單一 ticker 的最新快照
3. 前端 `stocks/[ticker]` 串接 profile API
4. Screener 結果卡先補 `market` badge
5. 視覺驗證後，再決定是否在結果卡加 `group_name`

Response 範例：

```json
{
  "total": 18,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "ticker": "2330",
      "name": "台積電",
      "industry": "半導體業",
      "match_score": 100,
      "matched_rules": [
        "毛利率 >= 30%",
        "EPS > 2",
        "毛利率較去年同季增加 >= 5 個百分點"
      ],
      "missing_metrics": [],
      "metrics": {
        "gross_margin": 55.1,
        "operating_margin": 42.3,
        "eps": 12.3,
        "share_capital_billion": 259.3,
        "revenue_yoy": 18.5,
        "gross_margin_yoy_delta": 6.2
      }
    }
  ]
}
```

## 15. Extended Profile Data Review

### 15.1 New Yahoo Data Domains

在 Yahoo 個股基本資料頁中，除 `公司基本資料` 外，還有三個值得入庫的資料域：

- `配股資訊`
- `財務資訊`
- `重要行事曆`

這三塊都應納入資料庫，但不應混入 `company_profiles`。原因如下：

- `company_profiles` 是公司識別與治理快照，偏向 identity layer
- `配股資訊` 是股利政策摘要，屬於資本回饋資料
- `財務資訊` 是 Yahoo 展示用的彙總財務快照，偏向 highlight layer
- `重要行事曆` 是事件時間軸，偏向 event layer

### 15.2 Table Ownership Decision

建議新增下列資料表：

1. `company_dividend_summaries`
- 儲存 profile 頁的配股摘要
- 一筆代表單一公司於某一資料時間的最新配股資訊

2. `company_financial_highlights`
- 儲存 profile 頁的獲利能力摘要
- 一筆代表單一公司某一季的展示型財務快照

3. `company_financial_highlight_eps`
- 儲存 `最新四季每股盈餘` 與 `最近四年每股盈餘`
- 以序列資料表處理，不塞進單一 JSON 欄位，方便 API 與前端直接使用

4. `company_calendar_events`
- 儲存 `重要行事曆`
- 以事件表處理，支援單點日期與日期區間

### 15.3 UI Placement Decision

`/design-consultation` 結論如下：

#### Screener 主列表

不導入這三塊詳細資料，只保留現有的輕量辨識資訊：

- `market`
- `industry`
- `group_name`

原因：

- screener 的任務是快速縮小名單，不是閱讀公司事件與配息細節
- 若將股利、行事曆與 highlight 全塞入結果卡，會顯著破壞掃描效率

#### 個股詳情頁 `/stocks/[ticker]`

這三塊資料應集中於個股頁，並排在財務趨勢之上或右側摘要區：

1. `Company Profile`
- 公司身份、治理與聯絡資訊

2. `Financial Highlights`
- 毛利率、營益率、ROA、ROE、稅前淨利率、每股淨值
- 最新四季 EPS 與最近四年 EPS

3. `Dividend Summary`
- 股利所屬期間
- 現金股利
- 盈餘配股
- 公積配股
- 股票股利
- 是否為預估值

4. `Important Calendar`
- 股東常會
- 配股發放日
- 現金股利發放日
- 除息 / 除權 / 停止過戶 / 停止融券事件

### 15.4 Product Decision

MVP 先完成資料落庫與 API 可讀取，不急著在 screener 主頁擴欄。

優先順序：

1. 先完成 schema 與 ETL
2. 再完成 stock detail API
3. 最後才決定哪些欄位要進入 `/stocks/[ticker]` 第一屏

## 16. Plan-Eng-Review: Extended Profile Data

### 16.1 Database Architecture

建議資料表與用途如下：

- `company_profiles`
  - 公司身份與治理資料
- `company_dividend_summaries`
  - 配股資訊
- `company_financial_highlights`
  - 財務摘要主表
- `company_financial_highlight_eps`
  - 財務摘要中的 EPS 序列
- `company_calendar_events`
  - 重要行事曆事件表

### 16.2 API Requirements

建議新增：

- `GET /api/v1/stocks/{ticker}/dividend-summary`
- `GET /api/v1/stocks/{ticker}/financial-highlights`
- `GET /api/v1/stocks/{ticker}/calendar`

可選聚合端點：

- `GET /api/v1/stocks/{ticker}/overview`

此聚合端點可回傳：

- 最新 `company_profiles`
- 最新 `company_dividend_summaries`
- 最新 `company_financial_highlights`
- `company_financial_highlight_eps`
- 最新 `company_calendar_events`

### 16.3 ETL Design

`etl/yahoo_profile.py` 應擴充為單頁多 section crawler，統一抓取：

- `公司基本資料`
- `配股資訊`
- `財務資訊`
- `重要行事曆`

內部應拆成獨立 parser：

- `parse_profile_section`
- `parse_dividend_section`
- `parse_financial_highlights_section`
- `parse_calendar_section`

### 16.4 Development Sequence

1. 新增 schema
2. 擴充 `etl/yahoo_profile.py`
3. 先以單一 ticker 驗證
4. 寫入 `twstock_fundamentals`
5. 再補 API 與前端 stock detail 串接

## 17. Match Score Draft

由於 MVP 僅支援 `全部符合`，結果仍需要有可排序差異，建議先採簡化版 `match_score`：

- 全部符合者才進結果集
- 以條件超額完成幅度計算 normalized score
- 每條規則各自計分後取平均，再轉成 `0-100`
- 前端不可寫死公式，保留後端可調整空間

## 18. MVP Copy

頁面標題：

- `用策略語言找股票`

副標：

- `依毛利率、營益率、EPS、股本與年增變化，快速篩出值得研究的名單。`

資料時間提示：

- `月營收最新資料：2025-12`
- `季資料最新資料：2025 Q4`

預設模板：

- `高毛利成長`
- `小股本高獲利`
- `毛利率改善`

空結果提示：

- `目前沒有符合條件的股票`
- `建議放寬 1-2 個條件，或先移除同比增幅限制`

## 19. Delivery Recommendation

建議 `/plan-eng-review` 依以下順序進行：

1. 先定稿 `metadata` 與 `query` API contract
2. 用假資料完成 `web/app/screener/page.tsx` 骨架
3. 串接 metadata API
4. 串接 query API
5. 最後補個股 diagnostics 與產業排名延伸功能

## 20. New Screener Conditions Review

### 20.1 Data Readiness Check

截至目前，以下資料已具備全市場覆蓋，可進入 screener 條件設計：

- `company_dividend_summaries`
- `company_financial_highlights`
- `company_financial_highlight_eps`
- `company_calendar_events`
- `company_profiles`

其中 `company_dividend_summaries`、`company_financial_highlights`、`company_calendar_events`
皆已覆蓋 ticker universe 的 1924 檔股票，可作為 MVP 條件來源。

### 20.2 Condition Classification Principle

條件分類不應依資料表名稱分，而應依使用者策略語言與決策順序分：

1. `財報資料`
- 高可比性、高頻使用、最適合當核心條件

2. `基本資料`
- 作為市場、規模、產業與身份條件

3. `股利政策`
- 適合補強配息 / 配股偏好的策略

4. `重要事件`
- 不屬於基本面優劣，而屬於交易時點條件

### 20.3 MVP Conditions

本輪只做以下 MVP 條件：

#### 財報資料

- `毛利率 >= X`
- `營業利益率 >= X`
- `EPS >= X`
- `毛利率較去年同季變化 >= X`
- `ROE >= X`
- `ROA >= X`
- `每股淨值 >= X`

#### 基本資料

- `市場別 = 上市 / 上櫃`
- `產業 = 某產業`
- `股本介於 A ~ B`
- `市值介於 A ~ B`

#### 股利政策

- `現金股利 >= X`

#### 重要事件

- `未來 N 天內有除息日`

### 20.4 Design Principles

1. 只有跨公司可比較的欄位，才做成 screener filter。
2. 只有覆蓋率高、定義穩定的欄位，才納入 MVP。
3. 主畫面優先放 `財報資料` 與 `基本資料`；股利與事件條件放在次層分組。
4. 條件要支援 4 種互動型態：
- threshold
- range
- select
- event window

5. 每個條件都要清楚標示資料基準：
- 最新季
- 最新月
- 最新快照
- 未來事件

### 20.5 UI Recommendation

Screener 條件區建議改為 4 個分組：

- `財報資料`
- `基本資料`
- `股利政策`
- `重要事件`

每個分組下仍沿用互動式條件列，但依條件型態分別呈現：

- threshold 類：單一數值輸入
- range 類：最小值 / 最大值雙欄
- select 類：下拉選單
- event 類：天數輸入

### 20.6 Result Explainability Principle

結果頁應維持精簡，但命中條件要能反映新分類：

- 財報條件命中
- 基本資料條件命中
- 股利條件命中
- 事件條件命中

結果卡不一定要展示所有欄位，但至少要保留 `matched rules` 讓使用者知道入選原因。

## 21. /plan-eng-review RFQ Draft

### 21.1 RFQ Goal

建立第一版「多分類 screener filter framework」，使現有 `/screener` 可支援：

- 財報資料篩選
- 基本資料篩選
- 股利政策篩選
- 重要事件篩選

並維持：

- metadata-driven 條件設定
- 全部符合模式
- 可解釋結果列表

### 21.2 RFQ Scope

#### Backend

1. 擴充 `ScreeningRequest`
- `min_roe`
- `min_roa`
- `min_book_value_per_share`
- `share_capital_min`
- `share_capital_max`
- `market_cap_min`
- `market_cap_max`
- `market`
- `min_cash_dividend`
- `upcoming_ex_dividend_within_days`

2. 擴充 screen query
- join `company_profiles`
- join `company_financial_highlights`
- join `company_dividend_summaries`
- join `company_calendar_events`

3. 擴充 metadata API
- 回傳可用市場別
- 回傳分類後的條件白名單
- 回傳新的 default filters

#### Frontend

1. 擴充 filter state 與 active rule state
2. 將條件區改為分組式 rule builder
3. 支援 4 種輸入型態：
- threshold
- range
- select
- event window

4. 結果卡與命中條件文字需支援新條件

### 21.3 RFQ Acceptance Criteria

以下條件成立時，視為 RFQ 完成：

1. `/api/v1/stocks/screen` 可接受並正確處理新條件
2. `/api/v1/screens/metadata` 可回傳新分類與預設值
3. `/screener` 可在 UI 上切換並送出新條件
4. 結果頁可顯示新條件的命中原因
5. `ROE`、`ROA`、`股本區間`、`市值區間`、`現金股利`、`未來 N 天內除息`
   至少需有 1 檔實際股票可驗證

### 21.4 MVP Delivery Order

1. 先改 API schema 與 query
2. 再改 metadata
3. 再改前端 rule builder
4. 最後做結果 explainability 與 QA
