from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Any, Iterable

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import SessionLocal
from etl.http import get_text
from etl.ticker_universe import DEFAULT_TICKER_UNIVERSE_PATH, load_ticker_universe
from etl.yahoo_symbols import yahoo_quote_symbols

YAHOO_PROFILE_URL = "https://tw.stock.yahoo.com/quote/{ticker}/profile"

SECTION_PROFILE = "公司基本資料"
SECTION_DIVIDEND = "配股資訊"
SECTION_FINANCIAL = "財務資訊"
SECTION_CALENDAR = "重要行事曆"

PAIR_HTML_PATTERN = re.compile(
    r"<span[^>]*>(?:<span>)?(?P<label>[^<]+)(?:</span>)?</span>"
    r"<div class=\"Py\(8px\)(?: D\(f\))? Pstart\(12px\) Bxz\(bb\)\">(?P<value>.*?)</div>",
    re.S,
)

PROFILE_LABEL_MAP = {
    "公司名稱": "company_name",
    "英文簡稱": "english_short_name",
    "市場別": "market",
    "產業類別": "industry",
    "發言人": "spokesperson",
    "代理發言人": "acting_spokesperson",
    "董事長": "chairman",
    "總經理": "general_manager",
    "總機電話": "phone",
    "傳真號碼": "fax",
    "電子郵件": "email",
    "公司網站": "website",
    "公司地址": "address",
    "股務代理": "stock_transfer_agent",
    "簽證會計師": "auditor",
    "所屬集團": "group_name",
    "主要經營業務": "business_summary",
    "成立時間": "established_date",
    "掛牌日期": "listed_date",
    "股本": "share_capital",
    "已發行普通股數": "issued_common_shares",
    "市值 (百萬)": "market_cap_million_twd",
    "董監持股比例(%)": "director_supervisor_holding_pct",
}

DIVIDEND_LABEL_MAP = {
    "股利所屬期間": "dividend_year",
    "盈餘配股": "earnings_stock_dividend",
    "現金股利": "cash_dividend",
    "公積配股": "capital_reserve_stock_dividend",
    "股票股利": "stock_dividend",
}

FINANCIAL_LABEL_MAP = {
    "營業毛利率": "gross_margin",
    "資產報酬率": "roa",
    "營業利益率": "operating_margin",
    "股東權益報酬率": "roe",
    "稅前淨利率": "pretax_margin",
    "每股淨值": "book_value_per_share",
}

HEADER_PATTERN = '<h2 class="Fz(24px) Fz(20px)--mobile Fw(b)">{heading}</h2>'


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", unescape(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in ("", "-", "--", "—"):
        return None
    return cleaned


def _extract_pair_entries(section_html: str) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for match in PAIR_HTML_PATTERN.finditer(section_html):
        label = _clean_text(match.group("label"))
        if label is None:
            continue
        entries.append(
            {
                "label": label,
                "value": _clean_text(match.group("value")),
                "raw_value_html": match.group("value"),
            }
        )
    return entries


def _extract_pairs(section_html: str) -> dict[str, str | None]:
    return {entry["label"]: entry["value"] for entry in _extract_pair_entries(section_html)}


def _parse_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        year, month, day = cleaned.split("/", 2)
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def _parse_date_range(value: str | None) -> tuple[date | None, date | None]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None, None
    if " - " not in cleaned:
        parsed = _parse_date(cleaned)
        return parsed, None
    start_text, end_text = cleaned.split(" - ", 1)
    return _parse_date(start_text), _parse_date(end_text)


def _parse_decimal(value: str | None) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace(",", "").replace("%", "").replace("元", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace(",", "").strip()
    try:
        return int(normalized)
    except ValueError:
        return None


def _parse_period_label(value: str | None) -> tuple[int | None, int | None]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None, None
    quarter_match = re.fullmatch(r"(\d{4})\s*Q([1-4])", cleaned)
    if quarter_match:
        return int(quarter_match.group(1)), int(quarter_match.group(2))
    year_match = re.fullmatch(r"(\d{4})", cleaned)
    if year_match:
        return int(year_match.group(1)), None
    return None, None


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _slice_section(html: str, heading: str, next_heading: str | None = None) -> str:
    start_marker = HEADER_PATTERN.format(heading=heading)
    start = html.find(start_marker)
    if start == -1:
        return ""
    section_start = html.rfind("<section", 0, start)
    if section_start == -1:
        section_start = start
    if next_heading is None:
        end = html.find("</section>", start)
        if end == -1:
            return html[section_start:]
        return html[section_start : end + len("</section>")]
    next_marker = HEADER_PATTERN.format(heading=next_heading)
    end = html.find(next_marker, start + len(start_marker))
    if end == -1:
        return html[section_start:]
    end_section = html.rfind("<section", start, end)
    if end_section == -1:
        end_section = end
    return html[section_start:end_section]


def _fetch_yahoo_profile_html(ticker: str) -> tuple[str | None, str | None]:
    html = None
    used_symbol = None
    last_http_error: requests.HTTPError | None = None
    last_request_error: requests.RequestException | None = None
    tried_symbols = yahoo_quote_symbols(ticker)

    for yahoo_ticker in tried_symbols:
        try:
            html = get_text(YAHOO_PROFILE_URL.format(ticker=yahoo_ticker), timeout=30)
            used_symbol = yahoo_ticker
            break
        except requests.HTTPError as exc:
            last_http_error = exc
            if exc.response is not None and exc.response.status_code in (404, 429):
                continue
            raise
        except requests.RequestException as exc:
            last_request_error = exc
            continue

    if html is None or used_symbol is None:
        if last_http_error is not None and last_http_error.response is not None:
            status_code = last_http_error.response.status_code
            if status_code == 404:
                print(f"[warn] yahoo profile not found for {ticker} (tried: {', '.join(tried_symbols)})")
                return None, None
            if status_code == 429:
                print(f"[warn] yahoo profile rate limited for {ticker} (tried: {', '.join(tried_symbols)})")
                return None, None
        if last_request_error is not None:
            print(
                f"[warn] yahoo profile request failed for {ticker} "
                f"(tried: {', '.join(tried_symbols)}): {last_request_error}"
            )
            return None, None
    return html, used_symbol


def _extract_data_date(html: str) -> date | None:
    match = re.search(r"資料時間：(\d{4}/\d{2}/\d{2})", html)
    return _parse_date(match.group(1) if match else None)


def _parse_profile_section(section_html: str, ticker: str, yahoo_symbol: str, data_date: date) -> dict[str, Any] | None:
    raw_pairs = _extract_pairs(section_html)
    if not raw_pairs:
        return None

    row = {
        "ticker": ticker.strip().upper().split(".", 1)[0],
        "yahoo_symbol": yahoo_symbol,
        "company_name": raw_pairs.get("公司名稱") or ticker,
        "english_short_name": raw_pairs.get("英文簡稱"),
        "market": raw_pairs.get("市場別"),
        "industry": raw_pairs.get("產業類別"),
        "spokesperson": raw_pairs.get("發言人"),
        "acting_spokesperson": raw_pairs.get("代理發言人"),
        "chairman": raw_pairs.get("董事長"),
        "general_manager": raw_pairs.get("總經理"),
        "phone": raw_pairs.get("總機電話"),
        "fax": raw_pairs.get("傳真號碼"),
        "email": raw_pairs.get("電子郵件"),
        "website": raw_pairs.get("公司網站"),
        "address": raw_pairs.get("公司地址"),
        "stock_transfer_agent": raw_pairs.get("股務代理"),
        "auditor": raw_pairs.get("簽證會計師"),
        "group_name": raw_pairs.get("所屬集團"),
        "business_summary": raw_pairs.get("主要經營業務"),
        "established_date": _parse_date(raw_pairs.get("成立時間")),
        "listed_date": _parse_date(raw_pairs.get("掛牌日期")),
        "share_capital": _parse_decimal(raw_pairs.get("股本")),
        "issued_common_shares": _parse_int(raw_pairs.get("已發行普通股數")),
        "market_cap_million_twd": _parse_decimal(raw_pairs.get("市值 (百萬)")),
        "director_supervisor_holding_pct": _parse_decimal(raw_pairs.get("董監持股比例(%)")),
        "data_date": data_date,
        "source": "yahoo",
        "source_url": YAHOO_PROFILE_URL.format(ticker=yahoo_symbol),
        "raw_payload": raw_pairs,
    }
    canonical_payload = {PROFILE_LABEL_MAP.get(label, label): value for label, value in sorted(raw_pairs.items())}
    row["raw_hash"] = _canonical_hash(canonical_payload)
    return row


def _parse_dividend_section(section_html: str, ticker: str, yahoo_symbol: str, data_date: date) -> dict[str, Any] | None:
    entries = _extract_pair_entries(section_html)
    if not entries:
        return None
    raw_pairs = {entry["label"]: entry["value"] for entry in entries}
    is_advance_notice = any("qsp-label-advance-notice" in (entry["raw_value_html"] or "") for entry in entries)
    row = {
        "ticker": ticker,
        "dividend_year": _parse_int(raw_pairs.get("股利所屬期間")),
        "cash_dividend": _parse_decimal(raw_pairs.get("現金股利")),
        "earnings_stock_dividend": _parse_decimal(raw_pairs.get("盈餘配股")),
        "capital_reserve_stock_dividend": _parse_decimal(raw_pairs.get("公積配股")),
        "stock_dividend": _parse_decimal(raw_pairs.get("股票股利")),
        "is_advance_notice": is_advance_notice,
        "data_date": data_date,
        "source": "yahoo",
        "source_url": YAHOO_PROFILE_URL.format(ticker=yahoo_symbol),
        "raw_payload": raw_pairs,
    }
    canonical_payload = {DIVIDEND_LABEL_MAP.get(label, label): value for label, value in sorted(raw_pairs.items())}
    canonical_payload["is_advance_notice"] = is_advance_notice
    row["raw_hash"] = _canonical_hash(canonical_payload)
    return row


def _parse_financial_highlights_section(
    section_html: str, ticker: str, yahoo_symbol: str, data_date: date
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not section_html:
        return None, []

    period_match = re.search(r"(\d{4})\s+Q([1-4])\s+獲利能力", section_html)
    if not period_match:
        return None, []
    fiscal_year = int(period_match.group(1))
    fiscal_quarter = int(period_match.group(2))

    eps_header_idx = section_html.find("最新四季每股盈餘")
    metrics_html = section_html[:eps_header_idx] if eps_header_idx != -1 else section_html
    raw_pairs = _extract_pairs(metrics_html)
    if not raw_pairs:
        return None, []

    row = {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "gross_margin": _parse_decimal(raw_pairs.get("營業毛利率")),
        "operating_margin": _parse_decimal(raw_pairs.get("營業利益率")),
        "roa": _parse_decimal(raw_pairs.get("資產報酬率")),
        "roe": _parse_decimal(raw_pairs.get("股東權益報酬率")),
        "pretax_margin": _parse_decimal(raw_pairs.get("稅前淨利率")),
        "book_value_per_share": _parse_decimal(raw_pairs.get("每股淨值")),
        "data_date": data_date,
        "source": "yahoo",
        "source_url": YAHOO_PROFILE_URL.format(ticker=yahoo_symbol),
        "raw_payload": raw_pairs,
    }
    canonical_payload = {FINANCIAL_LABEL_MAP.get(label, label): value for label, value in sorted(raw_pairs.items())}
    row["raw_hash"] = _canonical_hash(canonical_payload)

    eps_rows: list[dict[str, Any]] = []
    if eps_header_idx == -1:
        return row, eps_rows

    eps_html = section_html[eps_header_idx:]
    eps_entries = _extract_pair_entries(eps_html)
    quarterly_order = 0
    annual_order = 0
    for entry in eps_entries:
        label = entry["label"]
        value = entry["value"]
        if value is None:
            continue
        entry_fiscal_year, entry_fiscal_quarter = _parse_period_label(label)
        if entry_fiscal_year is None:
            continue
        if entry_fiscal_quarter is not None:
            series_type = "quarterly_eps"
            quarterly_order += 1
            display_order = quarterly_order
        else:
            series_type = "annual_eps"
            annual_order += 1
            display_order = annual_order
        eps_rows.append(
            {
                "ticker": ticker,
                "series_type": series_type,
                "period_label": label,
                "fiscal_year": entry_fiscal_year,
                "fiscal_quarter": entry_fiscal_quarter,
                "eps": _parse_decimal(value),
                "display_order": display_order,
                "data_date": data_date,
                "source": "yahoo",
                "source_url": YAHOO_PROFILE_URL.format(ticker=yahoo_symbol),
                "raw_hash": _canonical_hash(
                    {
                        "series_type": series_type,
                        "period_label": label,
                        "value": value,
                    }
                ),
            }
        )
    return row, eps_rows


def _parse_calendar_section(section_html: str, ticker: str, yahoo_symbol: str, data_date: date) -> list[dict[str, Any]]:
    if not section_html:
        return []
    rows: list[dict[str, Any]] = []
    source_url = YAHOO_PROFILE_URL.format(ticker=yahoo_symbol)

    split_idx = section_html.find("除息資料")
    summary_html = section_html[:split_idx] if split_idx != -1 else section_html
    for entry in _extract_pair_entries(summary_html):
        if entry["value"] is None:
            continue
        start_date, end_date = _parse_date_range(entry["value"])
        payload = {"section_key": "summary", "event_name": entry["label"], "value": entry["value"]}
        rows.append(
            {
                "ticker": ticker,
                "section_key": "summary",
                "event_name": entry["label"],
                "event_date": start_date,
                "event_end_date": end_date,
                "event_value_text": entry["value"],
                "data_date": data_date,
                "source": "yahoo",
                "source_url": source_url,
                "raw_payload": payload,
                "raw_hash": _canonical_hash(payload),
            }
        )

    if split_idx == -1:
        return rows

    detail_html = section_html[split_idx:]
    detail_entries = _extract_pair_entries(detail_html)
    for index, entry in enumerate(detail_entries):
        if entry["value"] is None:
            continue
        section_key = "ex_dividend" if index % 2 == 0 else "ex_right"
        start_date, end_date = _parse_date_range(entry["value"])
        payload = {"section_key": section_key, "event_name": entry["label"], "value": entry["value"]}
        rows.append(
            {
                "ticker": ticker,
                "section_key": section_key,
                "event_name": entry["label"],
                "event_date": start_date,
                "event_end_date": end_date,
                "event_value_text": entry["value"],
                "data_date": data_date,
                "source": "yahoo",
                "source_url": source_url,
                "raw_payload": payload,
                "raw_hash": _canonical_hash(payload),
            }
        )
    return rows


def fetch_yahoo_profile_bundle(ticker: str) -> dict[str, Any] | None:
    html, used_symbol = _fetch_yahoo_profile_html(ticker)
    if html is None or used_symbol is None:
        return None

    data_date = _extract_data_date(html)
    if data_date is None:
        return None

    ticker_key = ticker.strip().upper().split(".", 1)[0]
    profile_section = _slice_section(html, SECTION_PROFILE, SECTION_DIVIDEND)
    dividend_section = _slice_section(html, SECTION_DIVIDEND, SECTION_FINANCIAL)
    financial_section = _slice_section(html, SECTION_FINANCIAL, SECTION_CALENDAR)
    calendar_section = _slice_section(html, SECTION_CALENDAR)

    financial_highlights, financial_eps_rows = _parse_financial_highlights_section(
        financial_section, ticker_key, used_symbol, data_date
    )

    bundle = {
        "profile": _parse_profile_section(profile_section, ticker_key, used_symbol, data_date),
        "dividend_summary": _parse_dividend_section(dividend_section, ticker_key, used_symbol, data_date),
        "financial_highlights": financial_highlights,
        "financial_eps_series": financial_eps_rows,
        "calendar_events": _parse_calendar_section(calendar_section, ticker_key, used_symbol, data_date),
    }

    if all(
        value in (None, [], {})
        for value in (
            bundle["profile"],
            bundle["dividend_summary"],
            bundle["financial_highlights"],
            bundle["financial_eps_series"],
            bundle["calendar_events"],
        )
    ):
        return None
    return bundle


def fetch_yahoo_profile(ticker: str) -> dict[str, Any] | None:
    bundle = fetch_yahoo_profile_bundle(ticker)
    if bundle is None:
        return None
    return bundle["profile"]


def _upsert_company_row(db: Session, profile_row: dict[str, Any]) -> None:
    db.execute(
        text(
            """
            INSERT INTO companies (ticker, name, market, industry, source, raw_hash, last_synced_at)
            VALUES (:ticker, :company_name, :market, :industry, :source, :raw_hash, :last_synced_at)
            ON CONFLICT (ticker) DO UPDATE
            SET name = EXCLUDED.name,
                market = EXCLUDED.market,
                industry = EXCLUDED.industry,
                source = EXCLUDED.source,
                raw_hash = EXCLUDED.raw_hash,
                last_synced_at = EXCLUDED.last_synced_at
            """
        ),
        {
            "ticker": profile_row["ticker"],
            "company_name": profile_row["company_name"],
            "market": profile_row["market"],
            "industry": profile_row["industry"],
            "source": profile_row["source"],
            "raw_hash": profile_row["raw_hash"],
            "last_synced_at": datetime.utcnow(),
        },
    )


def _upsert_profile_row(db: Session, row: dict[str, Any]) -> int:
    raw_payload_json = json.dumps(row["raw_payload"], ensure_ascii=False, sort_keys=True)
    db.execute(
        text(
            """
            INSERT INTO company_profiles (
                ticker, yahoo_symbol, company_name, english_short_name, market, industry,
                spokesperson, acting_spokesperson, chairman, general_manager,
                phone, fax, email, website, address,
                stock_transfer_agent, auditor, group_name, business_summary,
                established_date, listed_date, share_capital, issued_common_shares,
                market_cap_million_twd, director_supervisor_holding_pct,
                data_date, source, source_url, raw_payload, raw_hash
            )
            VALUES (
                :ticker, :yahoo_symbol, :company_name, :english_short_name, :market, :industry,
                :spokesperson, :acting_spokesperson, :chairman, :general_manager,
                :phone, :fax, :email, :website, :address,
                :stock_transfer_agent, :auditor, :group_name, :business_summary,
                :established_date, :listed_date, :share_capital, :issued_common_shares,
                :market_cap_million_twd, :director_supervisor_holding_pct,
                :data_date, :source, :source_url, CAST(:raw_payload AS JSONB), :raw_hash
            )
            ON CONFLICT (ticker, data_date, source) DO UPDATE
            SET yahoo_symbol = EXCLUDED.yahoo_symbol,
                company_name = EXCLUDED.company_name,
                english_short_name = EXCLUDED.english_short_name,
                market = EXCLUDED.market,
                industry = EXCLUDED.industry,
                spokesperson = EXCLUDED.spokesperson,
                acting_spokesperson = EXCLUDED.acting_spokesperson,
                chairman = EXCLUDED.chairman,
                general_manager = EXCLUDED.general_manager,
                phone = EXCLUDED.phone,
                fax = EXCLUDED.fax,
                email = EXCLUDED.email,
                website = EXCLUDED.website,
                address = EXCLUDED.address,
                stock_transfer_agent = EXCLUDED.stock_transfer_agent,
                auditor = EXCLUDED.auditor,
                group_name = EXCLUDED.group_name,
                business_summary = EXCLUDED.business_summary,
                established_date = EXCLUDED.established_date,
                listed_date = EXCLUDED.listed_date,
                share_capital = EXCLUDED.share_capital,
                issued_common_shares = EXCLUDED.issued_common_shares,
                market_cap_million_twd = EXCLUDED.market_cap_million_twd,
                director_supervisor_holding_pct = EXCLUDED.director_supervisor_holding_pct,
                source_url = EXCLUDED.source_url,
                raw_payload = EXCLUDED.raw_payload,
                raw_hash = EXCLUDED.raw_hash,
                fetched_at = NOW()
            """
        ),
        {**row, "raw_payload": raw_payload_json},
    )
    return 1


def _upsert_dividend_summary(db: Session, row: dict[str, Any]) -> int:
    raw_payload_json = json.dumps(row["raw_payload"], ensure_ascii=False, sort_keys=True)
    db.execute(
        text(
            """
            INSERT INTO company_dividend_summaries (
                ticker, dividend_year, cash_dividend, earnings_stock_dividend,
                capital_reserve_stock_dividend, stock_dividend, is_advance_notice,
                data_date, source, source_url, raw_payload, raw_hash
            )
            VALUES (
                :ticker, :dividend_year, :cash_dividend, :earnings_stock_dividend,
                :capital_reserve_stock_dividend, :stock_dividend, :is_advance_notice,
                :data_date, :source, :source_url, CAST(:raw_payload AS JSONB), :raw_hash
            )
            ON CONFLICT (ticker, data_date, source) DO UPDATE
            SET dividend_year = EXCLUDED.dividend_year,
                cash_dividend = EXCLUDED.cash_dividend,
                earnings_stock_dividend = EXCLUDED.earnings_stock_dividend,
                capital_reserve_stock_dividend = EXCLUDED.capital_reserve_stock_dividend,
                stock_dividend = EXCLUDED.stock_dividend,
                is_advance_notice = EXCLUDED.is_advance_notice,
                source_url = EXCLUDED.source_url,
                raw_payload = EXCLUDED.raw_payload,
                raw_hash = EXCLUDED.raw_hash,
                fetched_at = NOW()
            """
        ),
        {**row, "raw_payload": raw_payload_json},
    )
    return 1


def _upsert_financial_highlights(db: Session, row: dict[str, Any]) -> int:
    raw_payload_json = json.dumps(row["raw_payload"], ensure_ascii=False, sort_keys=True)
    db.execute(
        text(
            """
            INSERT INTO company_financial_highlights (
                ticker, fiscal_year, fiscal_quarter,
                gross_margin, operating_margin, roa, roe, pretax_margin, book_value_per_share,
                data_date, source, source_url, raw_payload, raw_hash
            )
            VALUES (
                :ticker, :fiscal_year, :fiscal_quarter,
                :gross_margin, :operating_margin, :roa, :roe, :pretax_margin, :book_value_per_share,
                :data_date, :source, :source_url, CAST(:raw_payload AS JSONB), :raw_hash
            )
            ON CONFLICT (ticker, fiscal_year, fiscal_quarter, data_date, source) DO UPDATE
            SET gross_margin = EXCLUDED.gross_margin,
                operating_margin = EXCLUDED.operating_margin,
                roa = EXCLUDED.roa,
                roe = EXCLUDED.roe,
                pretax_margin = EXCLUDED.pretax_margin,
                book_value_per_share = EXCLUDED.book_value_per_share,
                source_url = EXCLUDED.source_url,
                raw_payload = EXCLUDED.raw_payload,
                raw_hash = EXCLUDED.raw_hash,
                fetched_at = NOW()
            """
        ),
        {**row, "raw_payload": raw_payload_json},
    )
    return 1


def _replace_financial_eps_series(db: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    base = rows[0]
    db.execute(
        text(
            """
            DELETE FROM company_financial_highlight_eps
            WHERE ticker = :ticker
              AND data_date = :data_date
              AND source = :source
            """
        ),
        {"ticker": base["ticker"], "data_date": base["data_date"], "source": base["source"]},
    )
    for row in rows:
        db.execute(
            text(
                """
                INSERT INTO company_financial_highlight_eps (
                    ticker, series_type, period_label, fiscal_year, fiscal_quarter,
                    eps, display_order, data_date, source, source_url, raw_hash
                )
                VALUES (
                    :ticker, :series_type, :period_label, :fiscal_year, :fiscal_quarter,
                    :eps, :display_order, :data_date, :source, :source_url, :raw_hash
                )
                """
            ),
            row,
        )
    return len(rows)


def _replace_calendar_events(db: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    base = rows[0]
    db.execute(
        text(
            """
            DELETE FROM company_calendar_events
            WHERE ticker = :ticker
              AND data_date = :data_date
              AND source = :source
            """
        ),
        {"ticker": base["ticker"], "data_date": base["data_date"], "source": base["source"]},
    )
    for row in rows:
        raw_payload_json = json.dumps(row["raw_payload"], ensure_ascii=False, sort_keys=True)
        db.execute(
            text(
                """
                INSERT INTO company_calendar_events (
                    ticker, section_key, event_name, event_date, event_end_date,
                    event_value_text, data_date, source, source_url, raw_payload, raw_hash
                )
                VALUES (
                    :ticker, :section_key, :event_name, :event_date, :event_end_date,
                    :event_value_text, :data_date, :source, :source_url, CAST(:raw_payload AS JSONB), :raw_hash
                )
                """
            ),
            {**row, "raw_payload": raw_payload_json},
        )
    return len(rows)


def upsert_yahoo_profile(db: Session, bundle: dict[str, Any] | None) -> int:
    if bundle is None:
        return 0

    total = 0
    profile_row = bundle.get("profile")
    if profile_row is not None:
        _upsert_company_row(db, profile_row)
        total += _upsert_profile_row(db, profile_row)

    dividend_row = bundle.get("dividend_summary")
    if dividend_row is not None:
        total += _upsert_dividend_summary(db, dividend_row)

    financial_row = bundle.get("financial_highlights")
    if financial_row is not None:
        total += _upsert_financial_highlights(db, financial_row)

    total += _replace_financial_eps_series(db, bundle.get("financial_eps_series", []))
    total += _replace_calendar_events(db, bundle.get("calendar_events", []))
    return total


def run_yahoo_profile_sync(ticker: str) -> int:
    bundle = fetch_yahoo_profile_bundle(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_profile(db, bundle)
        db.commit()
    return count


def run_yahoo_profile_batch(tickers: Iterable[str]) -> int:
    total = 0
    processed = 0
    with SessionLocal() as db:
        for ticker in tickers:
            bundle = fetch_yahoo_profile_bundle(ticker)
            total += upsert_yahoo_profile(db, bundle)
            db.commit()
            processed += 1
            if processed % 100 == 0:
                print(f"processed {processed} tickers")
    return total


def load_profile_targets(input_path: Path = DEFAULT_TICKER_UNIVERSE_PATH) -> list[str]:
    tickers = load_ticker_universe(input_path)
    print(f"loaded {len(tickers)} tickers from {input_path}")
    return tickers


def main() -> None:
    parser = argparse.ArgumentParser(description="Yahoo company profile crawler")
    parser.add_argument("target", nargs="?", help="single ticker (e.g. 2330)")
    parser.add_argument(
        "--all-tickers",
        action="store_true",
        help="crawl all tickers from the ticker universe JSON",
    )
    parser.add_argument(
        "--tickers-file",
        default=str(DEFAULT_TICKER_UNIVERSE_PATH),
        help="path to ticker universe JSON",
    )
    args = parser.parse_args()

    if args.all_tickers:
        tickers = load_profile_targets(Path(args.tickers_file))
        inserted = run_yahoo_profile_batch(tickers)
        print(f"inserted {inserted} profile-related rows for {len(tickers)} tickers")
        return

    target = (args.target or "2330").strip()
    if target.lower() == "all":
        tickers = load_profile_targets(Path(args.tickers_file))
        inserted = run_yahoo_profile_batch(tickers)
        print(f"inserted {inserted} profile-related rows for {len(tickers)} tickers")
        return

    inserted = run_yahoo_profile_sync(target)
    print(f"inserted {inserted} profile-related rows for {target}")


if __name__ == "__main__":
    main()
