from __future__ import annotations

from .yahoo_quarterly import (
    fetch_yahoo_income_statement,
    run_yahoo_income_sync,
    upsert_yahoo_income_statement,
)


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_income_sync(target)
    print(f"inserted {inserted} rows for {target}")
