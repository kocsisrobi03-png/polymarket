#!/usr/bin/env bash
set -euo pipefail

SERVICE="polymarket-focus-bridge.service"
APP_DIR="/root/polymarket"
SMOKE="$APP_DIR/smoke_test_bridge.sh"
BASE="http://127.0.0.1:8012/health"

echo "== restart service =="
systemctl restart "$SERVICE"

echo "== wait for health =="
for i in {1..20}; do
  if curl -fsS "$BASE" >/dev/null 2>&1; then
    echo "HEALTH_OK attempt=$i"
    break
  fi
  sleep 1
done

curl -fsS "$BASE" >/dev/null

echo "== service status =="
systemctl --no-pager --full status "$SERVICE" | sed -n '1,12p'

echo "== smoke test =="
"$SMOKE"

echo "RESTART_AND_VERIFY_OK"
