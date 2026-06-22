#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8012"
TICKER="KXFED-26OCT-T4.75"
SERIES="KXFED"

echo "== health =="
curl -s "$BASE/health"; echo
echo

echo "== latest_summary =="
curl -s "$BASE/latest_summary"; echo
echo

echo "== latest_ticker =="
curl -s "$BASE/latest_ticker?ticker=$TICKER"; echo
echo

echo "== latest_series =="
curl -s "$BASE/latest_series?series=$SERIES"; echo
echo

echo "== check_ticker =="
curl -s -X POST "$BASE/check_ticker" \
  -H 'Content-Type: application/json' \
  -d "{\"ticker\":\"$TICKER\"}"
echo
echo

echo "== run_export_and_check =="
curl -s -X POST "$BASE/run_export_and_check" \
  -H 'Content-Type: application/json' \
  -d "{\"ticker\":\"$TICKER\"}"
echo
