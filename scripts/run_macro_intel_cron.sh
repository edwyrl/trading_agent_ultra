#!/usr/bin/env bash

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/macro_intel_cron.log"
PY_BIN="$REPO_ROOT/.venv/bin/python"

mkdir -p "$LOG_DIR"

start_ts="$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "[$start_ts] macro_intel_cron start" >>"$LOG_FILE"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.env"
  set +a
fi

if [[ ! -x "$PY_BIN" ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] ERROR: python not found at $PY_BIN" >>"$LOG_FILE"
  exit 1
fi

cd "$REPO_ROOT" || exit 1

rc=0
"$PY_BIN" scripts/run_macro_intel_cycle.py --date "$(date +%F)" >>"$LOG_FILE" 2>&1 || rc=$?

end_ts="$(date '+%Y-%m-%d %H:%M:%S %z')"
echo "[$end_ts] macro_intel_cron end rc=$rc" >>"$LOG_FILE"
echo "" >>"$LOG_FILE"

exit "$rc"
