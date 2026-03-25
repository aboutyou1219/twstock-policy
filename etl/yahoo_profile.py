from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Iterable

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import SessionLocal
from etl.http import get_text
from etl.ticker_universe import DEFAULT_TICKER_UNIVERSE_PATH, load_ticker_universe
from etl.yahoo_symbols import yahoo_quote_symbols

YAHOO_PROFILE_URL = "https://tw.stock.yahoo.com/quote/{ticker}/profile"

PROFILE_SECTION_END_MARKERS = ("配股資訊", "財務資訊", "重要行事曆")
PROFILE_PAIR_PATTERN = re.compile(
    r"<span[^>]*><span>(?P<label>[^<]+)</span></span>"
    r"<div class=\"Py\(8px\) Pstart\(12px\) Bxz\(bb\)\">(?P<value>.*?)</div>",
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


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", unescape(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in ("", "-", "--", "—"):
        return None
    return cleaned


def _parse_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        year, month, day = cleaned.split("/", 2)
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        return None


def _parse_decimal(value: str | None) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace(",", "").replace("%", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.replace(",", "")
    try:
        return int(normalized)
    except ValueError:
        return None


def _slice_profile_section(html: str) -> str:
    anchor = 'id="main-2-QuoteProfile-Proxy"'
    start = html.find(anchor)
    if start == -1:
        return ""
    section = html[start:]
    end_positions = [section.find(marker) for marker in PROFILE_SECTION_END_MARKERS if section.find(marker) != -1]
    if end_positions:
        return section[: min(end_positions)]
    return section


def _extract_pairs(section_html: str) -> dict[str, str | None]:
    pairs: dict[str, str | None] = {}
    for match in PROFILE_PAIR_PATTERN.finditer(section_html):
        label = _clean_text(match.group("label"))
        if label is None:
            continue
        pairs[label] = _clean_text(match.group("value"))
    return pairs


def fetch_yahoo_profile(ticker: str) -> dict | None:
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
                return None
            if status_code == 429:
                print(f"[warn] yahoo profile rate limited for {ticker} (tried: {', '.join(tried_symbols)})")
                return None
        if last_request_error is not None:
            print(
                f"[warn] yahoo profile request failed for {ticker} "
                f"(tried: {', '.join(tried_symbols)}): {last_request_error}"
            )
            return None
        return None

    section_html = _slice_profile_section(html)
    if not section_html:
        return None

    data_date_match = re.search(r"資料時間：(\d{4}/\d{2}/\d{2})", section_html)
    data_date = _parse_date(data_date_match.group(1) if data_date_match else None)
    if data_date is None:
        return None

    raw_pairs = _extract_pairs(section_html)
    if not raw_pairs:
        return None

    row = {
        "ticker": ticker.strip().upper().split(".", 1)[0],
        "yahoo_symbol": used_symbol,
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
        "source_url": YAHOO_PROFILE_URL.format(ticker=used_symbol),
        "raw_payload": raw_pairs,
    }

    canonical_payload = {
        PROFILE_LABEL_MAP.get(label, label): value for label, value in sorted(raw_pairs.items())
    }
    row["raw_hash"] = hashlib.sha256(
        json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return row


def upsert_yahoo_profile(db: Session, row: dict | None) -> int:
    if row is None:
        return 0

    raw_payload_json = json.dumps(row["raw_payload"], ensure_ascii=False, sort_keys=True)

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
            "ticker": row["ticker"],
            "company_name": row["company_name"],
            "market": row["market"],
            "industry": row["industry"],
            "source": row["source"],
            "raw_hash": row["raw_hash"],
            "last_synced_at": datetime.utcnow(),
        },
    )

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
        {
            **row,
            "raw_payload": raw_payload_json,
        },
    )
    return 1


def run_yahoo_profile_sync(ticker: str) -> int:
    row = fetch_yahoo_profile(ticker)
    with SessionLocal() as db:
        count = upsert_yahoo_profile(db, row)
        db.commit()
    return count


def run_yahoo_profile_batch(tickers: Iterable[str]) -> int:
    total = 0
    processed = 0
    with SessionLocal() as db:
        for ticker in tickers:
            row = fetch_yahoo_profile(ticker)
            total += upsert_yahoo_profile(db, row)
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
        print(f"inserted {inserted} profile rows for {len(tickers)} tickers")
        return

    target = (args.target or "2330").strip()
    if target.lower() == "all":
        tickers = load_profile_targets(Path(args.tickers_file))
        inserted = run_yahoo_profile_batch(tickers)
        print(f"inserted {inserted} profile rows for {len(tickers)} tickers")
        return

    inserted = run_yahoo_profile_sync(target)
    print(f"inserted {inserted} profile rows for {target}")


if __name__ == "__main__":
    main()
