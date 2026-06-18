import requests, json

events = requests.get("https://gamma-api.polymarket.com/events", params={"active":"true","closed":"false","limit":20,"order":"volume","ascending":"false"}, timeout=30).json()
rows = []
for ev in events:
    for m in (ev.get("markets") or []):
        prices = m.get("outcomePrices")
        if isinstance(prices, str):
            prices = json.loads(prices)
        if not (m.get("active", False) and (not m.get("closed", True)) and m.get("acceptingOrders", False) and isinstance(prices, list) and len(prices) == 2):
            continue
        yes = float(prices[0])
        vol = float(m.get("volume") or 0)
        liq = float(m.get("liquidity") or 0)
        if yes < 0.15 or yes > 0.40:
            continue
        if vol < 100000:
            continue
        if liq < 10000:
            continue
        rows.append((vol, ev.get("title"), m.get("question"), prices, liq, m.get("slug")))
rows.sort(reverse=True, key=lambda x: x[0])
print("FOCUSED MARKETS:", len(rows))
for i, row in enumerate(rows[:10], start=1):
    print(f"{i}. {row[2]}")
    print(f"   event: {row[1]}")
    print(f"   prices: {row[3]}")
    print(f"   volume: {row[0]}")
    print(f"   liquidity: {row[4]}")
    print(f"   slug: {row[5]}")
    print()
