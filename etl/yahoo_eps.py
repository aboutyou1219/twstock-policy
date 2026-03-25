from __future__ import annotations

from .yahoo_quarterly import fetch_yahoo_eps, run_yahoo_eps_sync, upsert_yahoo_eps


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "2330"
    inserted = run_yahoo_eps_sync(target)
    print(f"inserted {inserted} rows for {target}")
