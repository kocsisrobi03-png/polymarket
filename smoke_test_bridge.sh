#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8012"
TICKER="KXFED-26OCT-T4.75"
SERIES="KXFED"

check_json() {
  local name="$1"
  local json="$2"
  python3 - "$name" "$json" <<'PY'
import json
import sys

name = sys.argv[1]
raw = sys.argv[2]
data = json.loads(raw)

assert data.get("ok") is True, f"{name}: ok != true"

if name == "health":
    assert data.get("status") == "ok", f"{name}: bad status"
    assert data["data"].get("latest_json_exists") is True, f"{name}: latest json missing"

elif name == "latest_summary":
    assert data.get("status") == "ok", f"{name}: bad status"
    assert data["data"].get("total_markets", 0) > 0, f"{name}: no markets"

elif name == "latest_ticker":
    assert data.get("status") == "found", f"{name}: ticker not found"
    assert data.get("count") == 1, f"{name}: bad count"

elif name == "latest_series":
    assert data.get("status") == "found", f"{name}: series not found"
    assert data.get("count", 0) > 0, f"{name}: empty series"

elif name == "check_ticker":
    assert data.get("status") == "found", f"{name}: ticker not found"
    assert data["data"].get("latest_found") is True, f"{name}: latest_found false"

elif name == "run_export_and_check":
    assert data.get("status") == "found", f"{name}: ticker not found after export"
    assert data["data"].get("export_ok") is True, f"{name}: export failed"
    assert data["data"].get("latest_found") is True, f"{name}: latest_found false"

print(f"OK {name}")
PY
}

echo "== health =="
resp="$(curl -s "$BASE/health")"
echo "$resp"
check_json "health" "$resp"
echo

echo "== latest_summary =="
resp="$(curl -s "$BASE/latest_summary")"
echo "$resp"
check_json "latest_summary" "$resp"
echo

echo "== latest_ticker =="
resp="$(curl -s "$BASE/latest_ticker?ticker=$TICKER")"
echo "$resp"
check_json "latest_ticker" "$resp"
echo

echo "== latest_series =="
resp="$(curl -s "$BASE/latest_series?series=$SERIES")"
echo "$resp"
check_json "latest_series" "$resp"
echo

echo "== check_ticker =="
resp="$(curl -s -X POST "$BASE/check_ticker" \
  -H 'Content-Type: application/json' \
  -d "{\"ticker\":\"$TICKER\"}")"
echo "$resp"
check_json "check_ticker" "$resp"
echo

echo "== run_export_and_check =="
resp="$(curl -s -X POST "$BASE/run_export_and_check" \
  -H 'Content-Type: application/json' \
  -d "{\"ticker\":\"$TICKER\"}")"
echo "$resp"
check_json "run_export_and_check" "$resp"
echo

echo "ALL_SMOKE_TESTS_PASSED"

