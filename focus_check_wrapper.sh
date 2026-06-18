#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/polymarket"
VENV_ACTIVATE="$PROJECT_DIR/.venv/bin/activate"
SCRIPT_NAME="run_focus_export_clean.py"
LATEST_JSON="$PROJECT_DIR/polymarket_focus_latest.json"
LOG_FILE="/tmp/run_focus_export_clean.log"
TARGET_TICKER="${1:-KXFED-26SEP-T3.75}"

cd "$PROJECT_DIR"

if [[ ! -f "$VENV_ACTIVATE" ]]; then
  echo "ERROR: missing venv activate script at $VENV_ACTIVATE" >&2
  exit 1
fi

source "$VENV_ACTIVATE"

python3 -c "import requests" >/dev/null 2>&1 || {
  echo "ERROR: requests is not installed in the virtualenv" >&2
  exit 1
}

python3 "$SCRIPT_NAME" | tee "$LOG_FILE"

echo
echo "LATEST_JSON: $LATEST_JSON"
echo "LOG_FILE: $LOG_FILE"

if grep -n "$TARGET_TICKER" "$LATEST_JSON"; then
  echo "PRESENT: $TARGET_TICKER"
else
  echo "NOT_PRESENT: $TARGET_TICKER"
fi
