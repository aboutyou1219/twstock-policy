#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/victor/Documents/stock/twstock-policy"
PYTHON="/home/victor/Documents/stock/.twstock/bin/python"
LOG_DIR="$ROOT/logs/etl-cron"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/monthly-revenue-$STAMP.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export ETL_QPS="${ETL_QPS:-1}"

{
  echo "started_at=$(date --iso-8601=seconds)"
  echo "job=monthly_revenue_full"
  echo "root=$ROOT"
  "$PYTHON" -m etl.ticker_universe
  "$PYTHON" -m etl.yahoo_revenue_batch --all
  echo "finished_at=$(date --iso-8601=seconds)"
} 2>&1 | tee "$LOG_FILE"
