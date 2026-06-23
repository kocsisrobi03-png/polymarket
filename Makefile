.PHONY: health smoke restart verify status log latest

health:
	curl -s http://127.0.0.1:8012/health

smoke:
	/root/polymarket/smoke_test_bridge.sh

restart:
	systemctl restart polymarket-focus-bridge.service

verify:
	/root/polymarket/restart_and_verify.sh

status:
	systemctl --no-pager --full status polymarket-focus-bridge.service | sed -n '1,20p'

log:
	journalctl -u polymarket-focus-bridge.service -n 50 --no-pager

latest:
	ls -lh /root/polymarket/polymarket_focus_latest.*
