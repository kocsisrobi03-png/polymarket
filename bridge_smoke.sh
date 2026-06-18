#!/usr/bin/env bash
set -euo pipefail

curl -s http://127.0.0.1:8012/health; echo
curl -s http://127.0.0.1:8012/latest_summary; echo
curl -s "http://127.0.0.1:8012/latest_markets?series=KXFED&contains=26OCT&limit=10"; echo
curl -s -X POST http://127.0.0.1:8012/check_series -H 'Content-Type: application/json' -d '{"series":"KXFED"}'; echo
curl -s -X POST http://127.0.0.1:8012/check_ticker -H 'Content-Type: application/json' -d '{"ticker":"KXFED-26OCT-T4.75"}'; echo
curl -s -X POST http://127.0.0.1:8012/run_export; echo
