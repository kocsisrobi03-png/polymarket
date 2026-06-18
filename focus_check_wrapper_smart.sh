#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/root/polymarket"
VENV_ACTIVATE="$PROJECT_DIR/.venv/bin/activate"
SCRIPT_NAME="run_focus_export_clean.py"
LATEST_JSON="$PROJECT_DIR/polymarket_focus_latest.json"
LOG_FILE="/tmp/run_focus_export_clean.log"
TARGET_RAW="${1:-KXFED-26SEP-T3.75}"

cd "$PROJECT_DIR"

if [[ ! -f "$VENV_ACTIVATE" ]]; then
  echo "ERROR: missing venv activate script at $VENV_ACTIVATE" >&2
  echo "STATUS=error"
  exit 20
fi

source "$VENV_ACTIVATE"

python3 -c "import requests" >/dev/null 2>&1 || {
  echo "ERROR: requests is not installed in the virtualenv" >&2
  echo "STATUS=error"
  exit 20
}

python3 "$SCRIPT_NAME" > "$LOG_FILE" 2>&1 || {
  echo "ERROR: export script failed" >&2
  echo "STATUS=error"
  exit 20
}

echo "RUN_OK"
echo "LATEST_JSON=$LATEST_JSON"
echo "LOG_FILE=$LOG_FILE"
echo "TARGET=$TARGET_RAW"

event_prefix="${TARGET_RAW%-T*}"
threshold_part=""
if [[ "$TARGET_RAW" == *-T* ]]; then
  threshold_part="${TARGET_RAW##*-T}"
fi
series_prefix="${TARGET_RAW%%-*}"

exact_matches="$(grep -nF "\"platform_market_id\": \"$TARGET_RAW\"" "$LATEST_JSON" || true)"
event_matches=""
threshold_matches=""
series_matches=""

if [[ -n "$event_prefix" && "$event_prefix" != "$TARGET_RAW" ]]; then
  event_matches="$(grep -nF "\"platform_market_id\": \"$event_prefix" "$LATEST_JSON" || true)"
fi

if [[ -n "$threshold_part" ]]; then
  threshold_matches="$(grep -nF "\"platform_market_id\":" "$LATEST_JSON" | grep -F -- "-T$threshold_part\"" || true)"
fi

if [[ -n "$series_prefix" && "$series_prefix" != "$TARGET_RAW" ]]; then
  series_matches="$(grep -nF "\"platform_market_id\": \"$series_prefix" "$LATEST_JSON" || true)"
fi

exact_count=0
event_count=0
threshold_count=0
series_count=0

[[ -n "$exact_matches" ]] && exact_count="$(printf '%s\n' "$exact_matches" | wc -l)"
[[ -n "$event_matches" ]] && event_count="$(printf '%s\n' "$event_matches" | wc -l)"
[[ -n "$threshold_matches" ]] && threshold_count="$(printf '%s\n' "$threshold_matches" | wc -l)"
[[ -n "$series_matches" ]] && series_count="$(printf '%s\n' "$series_matches" | wc -l)"

echo "EXACT_MATCHES=$exact_count"
echo "EVENT_MATCHES=$event_count"
echo "THRESHOLD_MATCHES=$threshold_count"
echo "SERIES_MATCHES=$series_count"

if [[ "$exact_count" -gt 0 ]]; then
  printf '%s\n' "$exact_matches"
  echo "PRESENT: $TARGET_RAW"
  echo "STATUS=present"
  exit 0
fi

echo "NOT_PRESENT: $TARGET_RAW"
echo "STATUS=not_present"

echo
echo "EVENT_PREFIX_MARKETS:"
if [[ -n "$event_matches" ]]; then
  printf '%s\n' "$event_matches"
else
  echo "(none)"
fi

echo
echo "THRESHOLD_MARKETS:"
if [[ -n "$threshold_matches" ]]; then
  printf '%s\n' "$threshold_matches"
else
  echo "(none)"
fi

echo
echo "SERIES_MARKETS:"
if [[ -n "$series_matches" ]]; then
  printf '%s\n' "$series_matches"
else
  echo "(none)"
fi

exit 10
