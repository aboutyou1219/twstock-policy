from __future__ import annotations

from .yahoo_quarterly import (
    fetch_yahoo_cash_flow,
    run_yahoo_cash_flow_sync,
    upsert_yahoo_cash_flow,
)


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_cash_flow_sync(target)
    print(f"inserted {inserted} rows for {target}")
