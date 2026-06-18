import requests, json, csv, datetime

today = datetime.date.today().isoformat()
filename = f"polymarket_focus_{today}.csv"
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
        no = float(prices[1])
        vol = float(m.get("volume") or 0)
        liq = float(m.get("liquidity") or 0)
        if yes < 0.15 or yes > 0.40:
            continue
        if vol < 100000:
            continue
        if liq < 10000:
            continue
        rows.append([ev.get("title"), m.get("question"), m.get("slug"), yes, no, vol, liq])
rows.sort(key=lambda x: x[5], reverse=True)
with open(filename, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["event","question","slug","price_yes","price_no","volume","liquidity"])
    w.writerows(rows)
print("CSV_ROWS:", len(rows))
print("CSV_FILE:", filename)
