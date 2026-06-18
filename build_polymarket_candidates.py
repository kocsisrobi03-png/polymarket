nano test_open_markets.py
import requests, json

events = requests.get(
    "https://gamma-api.polymarket.com/events",
    params={
        "active": "true",
        "closed": "false",
        "limit": 20,
        "order": "volume",
        "ascending": "false",
    },
    timeout=30,
).json()

count = 0

for ev in events:
    for m in (ev.get("markets") or []):
        prices = m.get("outcomePrices")
        if isinstance(prices, str):
            prices = json.loads(prices)

        ok = (
            m.get("active", False)
            and not m.get("closed", True)
            and m.get("acceptingOrders", False)
            and isinstance(prices, list)
            and len(prices) == 2
        )

        if ok:
            count += 1

print("EVENTS:", len(events))
print("OPEN_MARKETS:", count)

