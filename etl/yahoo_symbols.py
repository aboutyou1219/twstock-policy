from __future__ import annotations

import twstock


def yahoo_quote_symbols(ticker: str) -> list[str]:
    base = ticker.strip().upper().split(".", 1)[0]
    info = twstock.codes.get(base)
    symbols = [base]
    if info is None:
        return symbols
    if info.market == "上市":
        symbols.append(f"{base}.TW")
    elif info.market == "上櫃":
        symbols.append(f"{base}.TWO")
    return symbols
