# Polymarket Focus Bridge

FastAPI bridge for Polymarket/Kalshi focus export, local checks, and simple bridge operations.

## Daily ops

### Health
```bash
make health
```

### Smoke test
```bash
make smoke
```

### Restart and verify
```bash
make verify
```

### Service status
```bash
make status
```

### Recent logs
```bash
make log
```

### Latest export files
```bash
make latest
```

## API endpoints

### GET /health
Bridge health and latest export file presence.

### POST /run_export
Run fresh export and return short execution summary.

### POST /check_ticker
Check whether a ticker exists in the current latest JSON export.

Example:
```bash
curl -s -X POST "http://127.0.0.1:8012/check_ticker" \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"KXFED-EXAMPLE"}'
```

### POST /run_export_and_check
Run export, then check whether a ticker exists in the refreshed latest JSON.

### POST /check_series
Check whether a series prefix exists in the latest JSON export.

### GET /latest_markets
List latest normalized markets, optionally filtered.

Examples:
```bash
curl -s "http://127.0.0.1:8012/latest_markets"
curl -s "http://127.0.0.1:8012/latest_markets?limit=10"
curl -s "http://127.0.0.1:8012/latest_markets?event=KXFED"
curl -s "http://127.0.0.1:8012/latest_markets?platform=KALSHI"
```

### GET /latest_ticker
Get one normalized market by ticker.

Example:
```bash
curl -s "http://127.0.0.1:8012/latest_ticker?ticker=KXFED-EXAMPLE"
```

### GET /latest_series
Get normalized markets matching a series prefix.

Example:
```bash
curl -s "http://127.0.0.1:8012/latest_series?series=KXFED"
```

### GET /latest_summary
Get quick counts by event and platform.

Example:
```bash
curl -s "http://127.0.0.1:8012/latest_summary"
```

## Important files

- `focus_command_bridge.py` — FastAPI bridge
- `run_focus_export_clean.py` — normalized export builder
- `smoke_test_bridge.sh` — dynamic endpoint smoke test with assertions
- `restart_and_verify.sh` — restart service, wait for health, run smoke test
- `Makefile` — shortcut commands for daily operations

## Service

- `polymarket-focus-bridge.service`
- bind: `127.0.0.1:8012`

## Export outputs

Main generated files:
- `polymarket_focus_latest.csv`
- `polymarket_focus_latest.json`

Timestamped files are also written on each export run and older exports are cleaned up automatically.

## Notes

- Smoke test uses a dynamic series lookup instead of relying on one fixed ticker.
- Export output is intentionally short and stable for bridge usage.
- Market rows are deduplicated and sorted before writing latest files.
