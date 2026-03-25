from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import twstock

DEFAULT_TICKER_UNIVERSE_PATH = Path("data/tickers/twstock_tickers.json")


def build_ticker_universe() -> dict:
    tickers = [
        code
        for code, info in twstock.codes.items()
        if info.type == "股票"
        and info.market in ["上市", "上櫃"]
        and code.isdigit()
        and len(code) == 4
    ]
    tickers = sorted(tickers, key=int)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "twstock.codes",
        "filters": {
            "type": "股票",
            "markets": ["上市", "上櫃"],
            "digits_only": True,
            "code_length": 4,
        },
        "count": len(tickers),
        "tickers": tickers,
    }


def save_ticker_universe(output_path: Path = DEFAULT_TICKER_UNIVERSE_PATH) -> Path:
    payload = build_ticker_universe()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_ticker_universe(input_path: Path = DEFAULT_TICKER_UNIVERSE_PATH) -> list[str]:
    if input_path.exists():
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        tickers = payload.get("tickers", [])
        return [str(ticker) for ticker in tickers]
    return build_ticker_universe()["tickers"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a reusable TW stock ticker universe file")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_TICKER_UNIVERSE_PATH),
        help="output JSON file path",
    )
    args = parser.parse_args()

    output_path = save_ticker_universe(Path(args.output))
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    print(f"saved ticker universe to {output_path}")
    print(f"count={payload['count']}")


if __name__ == "__main__":
    main()
