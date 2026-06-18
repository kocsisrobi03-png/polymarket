import requests, json

events = requests.get("https://gamma-api.polymarket.com/events", params={"active":"true","closed":"false","limit":20,"order":"volume","ascending":"false"}, timeout=30).json()
rows = []
for ev in events:
    for m in (ev.get("markets") or []):
        prices = m.get("outcomePrices")
        if isinstance(prices, str):
            prices = json.loads(prices)
        ok = m.get("active", False) and (not m.get("closed", True)) and m.get("acceptingOrders", False) and isinstance(prices, list) and len(prices) == 2
        if ok:
            rows.append((m.get("volume") or 0, ev.get("title"), m.get("question"), prices, m.get("slug")))
rows.sort(reverse=True, key=lambda x: float(x[0]))
print("TOP OPEN MARKETS:")
for i, row in enumerate(rows[:15], start=1):
    print(f"{i}. {row[2]}")
    print(f"   event: {row[1]}")
    print(f"   prices: {row[3]}")
    print(f"   volume: {row[0]}")
    print(f"   slug: {row[4]}")
    print()
