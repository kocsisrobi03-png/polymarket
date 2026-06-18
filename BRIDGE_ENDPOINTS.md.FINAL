# Polymarket Focus Bridge

## Base
http://127.0.0.1:8012

## GET /health
Returns:
- ok
- status
- count
- data.root
- data.wrapper_exists
- data.export_exists
- data.latest_json_exists

## GET /latest_summary
Returns:
- ok
- status
- count
- data.top_series
- data.file

## GET /latest_markets?series=...&contains=...&limit=...
Returns:
- ok
- status
- count
- data.series
- data.contains
- data.limit
- data.markets

## POST /check_series
JSON body:
{"series":"KXFED"}

## POST /check_ticker
JSON body:
{"ticker":"KXFED-26OCT-T4.75"}

## POST /run_export
No body

## Command response schema
- ok
- status
- count
- data.stdout
- data.stderr
- returncode
