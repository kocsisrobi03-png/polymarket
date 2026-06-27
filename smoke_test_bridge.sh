#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8012"
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

elif name == "latest_series":
    assert data.get("status") == "found", f"{name}: series not found"
    assert data.get("count", 0) > 0, f"{name}: empty series"

elif name == "latest_ticker":
    assert data.get("status") == "found", f"{name}: ticker not found"
    assert data.get("count") == 1, f"{name}: bad count"

elif name == "check_ticker":
    assert data.get("status") == "found", f"{name}: ticker not found"
    assert data["data"].get("latest_found") is True, f"{name}: latest_found false"

elif name == "run_export_and_check":
    assert data["data"].get("export_ok") is True, f"{name}: export failed"
    assert data.get("status") in ("found", "not_found"), f"{name}: unexpected status"

print(f"OK {name}")
PY
}

extract_first_ticker() {
  local json="$1"
  python3 - "$json" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
markets = data.get("data", {}).get("markets", [])
if not markets:
    raise SystemExit("no markets in latest_series")
ticker = markets[0].get("platform_market_id")
if not ticker:
    raise SystemExit("missing platform_market_id")
print(ticker)
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

echo "== latest_series =="
resp="$(curl -s "$BASE/latest_series?series=$SERIES")"
echo "$resp"
check_json "latest_series" "$resp"
echo

TICKER="$(extract_first_ticker "$resp")"
echo "USING_TICKER=$TICKER"
echo

echo "== latest_ticker =="
resp="$(curl -s "$BASE/latest_ticker?ticker=$TICKER")"
echo "$resp"
check_json "latest_ticker" "$resp"
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
echo "== latest_ticker not_found =="
resp="$(curl -s "$BASE/latest_ticker?ticker=NOPE-TEST")"
echo "$resp"
python3 - "$resp" <<'PY'
import json
import sys
data = json.loads(sys.argv[1])
assert data.get("ok") is True
assert data.get("status") == "not_found"
assert data.get("count") == 0
PY
echo

echo "== check_ticker not_found =="
resp="$(curl -s -X POST "$BASE/check_ticker" \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"NOPE-TEST"}')"
echo "$resp"
python3 - "$resp" <<'PY'
import json
import sys
data = json.loads(sys.argv[1])
assert data.get("ok") is True
assert data.get("status") == "not_found"
assert data.get("count") == 0
PY
echo

echo "== latest_series not_found =="
resp="$(curl -s "$BASE/latest_series?series=NOPE")"
echo "$resp"
python3 - "$resp" <<'PY'
import json
import sys
data = json.loads(sys.argv[1])
assert data.get("ok") is True
assert data.get("status") == "not_found"
assert data.get("count") == 0
PY
echo

echo "== check_series not_found =="
resp="$(curl -s -X POST "$BASE/check_series" \
  -H 'Content-Type: application/json' \
  -d '{"series":"NOPE"}')"
echo "$resp"
python3 - "$resp" <<'PY'
import json
import sys
data = json.loads(sys.argv[1])
assert data.get("ok") is True
assert data.get("status") == "not_found"
assert data.get("count") == 0
PY
echo
echo "ALL_SMOKE_TESTS_PASSED"
