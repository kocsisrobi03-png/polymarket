cat > /root/polymarket/run_focus_export_clean.py <<'PY'
#!/usr/bin/env python3

import csv
import datetime
import glob
import json
import os
import shutil
import tempfile

import requests


SCHEMA_VERSION = "v6.0-clean"

DEBUG = False

ENABLE_POLYMARKET = True
ENABLE_KALSHI = True

KALSHI_MODE = "macro_politics"
KALSHI_ALLOWED_TYPES = {"politics", "macro"}

POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com/events"
POLYMARKET_PARAMS = {
    "active": "true",
    "closed": "false",
    "limit": 50,
    "order": "volume",
    "ascending": "false",
}

KALSHI_MARKETS_URL = "https://external-api.kalshi.com/trade-api/v2/markets"
KALSHI_SERIES_URL = "https://external-api.kalshi.com/trade-api/v2/series"

KALSHI_MARKETS_PARAMS = {
    "limit": 100,
    "mve_filter": "exclude",
}

KALSHI_SERIES_CATEGORIES = [
    "politics",
    "economics",
    "financials",
]

KALSHI_FALLBACK_SERIES_ALLOWLIST = [
    "KXFED",
    "KXGDP",
    "KXFFR",
    "KXINFLATION",
    "KXUSPRES",
]

KALSHI_SERIES_LIMIT = 200

PRICE_MIN = 0.15
PRICE_MAX = 0.40

POLYMARKET_VOLUME_MIN = 100000
POLYMARKET_LIQUIDITY_MIN = 10000

KALSHI_VOLUME_MIN = 0
KALSHI_LIQUIDITY_MIN = 0

KALSHI_MAX_PAGES = 10

TIMEOUT = 30
KEEP_LATEST_COUNT = 30
FILE_MODE = 0o644


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value)


def parse_prices(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def parse_iso_datetime(value):
    if not value or not isinstance(value, str):
        return None

    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw.replace("Z", "+00:00")

    try:
        dt = datetime.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except ValueError:
        return None


def normalize_text(value):
    return " ".join(safe_str(value).strip().lower().split())


def debug_print(*args):
    if DEBUG:
        print(*args, flush=True)


def set_file_mode(path):
    os.chmod(path, FILE_MODE)


def write_csv_atomic(path, header, rows):
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_focus_", suffix=".csv", dir=directory)
    os.close(fd)
    try:
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(tmp_path, path)
        set_file_mode(path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def write_json_atomic(path, data):
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_focus_", suffix=".json", dir=directory)
    os.close(fd)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        set_file_mode(path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def refresh_latest_file(src, dst):
    shutil.copyfile(src, dst)
    set_file_mode(dst)


def cleanup_old_exports(base_dir, keep_count):
    deleted = []

    for pattern in ("polymarket_focus_*.csv", "polymarket_focus_*.json"):
        files = []
        for path in glob.glob(os.path.join(base_dir, pattern)):
            name = os.path.basename(path)
            if "latest" in name:
                continue
            files.append(path)

        files.sort(key=os.path.getmtime, reverse=True)
        for stale in files[keep_count:]:
            try:
                os.remove(stale)
                deleted.append(stale)
            except FileNotFoundError:
                pass

    debug_print("DELETED_OLD_FILES:", len(deleted))


def calc_score(probability, volume, liquidity):
    return (probability * 100.0) + (volume / 100000.0) + (liquidity / 10000.0)


def detect_market_type(event_title, question):
    text = normalize_text(f"{event_title} {question}")

    politics_terms = [
        "president", "presidential", "senate", "house", "governor", "election",
        "elections", "primary", "primaries", "congress", "trump", "biden",
        "democrat", "republican", "parliament", "prime minister", "coalition",
        "referendum", "mayor", "politics", "political",
    ]
    macro_terms = [
        "fed", "fomc", "interest rate", "interest rates", "inflation", "cpi",
        "ppi", "gdp", "jobs", "payrolls", "unemployment", "housing", "oil",
        "crude", "fx", "foreign exchange", "central bank", "yield", "treasury",
        "economy", "economic", "financial", "rates",
    ]
    sports_terms = [
        "nba", "nfl", "mlb", "nhl", "soccer", "golf", "tennis", "pga",
        "championship", "round 1", "round 2", "top 10", "lead at the end",
        "vs ", "first inning", "touchdown", "goal", "match",
    ]

    if any(term in text for term in sports_terms):
        return "sports"
    if any(term in text for term in politics_terms):
        return "politics"
    if any(term in text for term in macro_terms):
        return "macro"
    return "other"


def build_standard_record(
    source,
    platform_market_id,
    event_title,
    question,
    slug,
    probability,
    volume,
    liquidity,
    now_utc,
    resolution_dt,
):
    hours_to_resolution = None
    resolution_time = ""

    if resolution_dt is not None:
        resolution_time = resolution_dt.isoformat()
        hours_to_resolution = round((resolution_dt - now_utc).total_seconds() / 3600.0, 4)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "platform_market_id": safe_str(platform_market_id),
        "market_type": detect_market_type(event_title, question),
        "event": safe_str(event_title),
        "question": safe_str(question),
        "slug": safe_str(slug),
        "probability": round(float(probability), 6),
        "volume": round(float(volume), 2),
        "liquidity": round(float(liquidity), 2),
        "timestamp": now_utc.isoformat(),
        "resolution_time": resolution_time,
        "hours_to_resolution": hours_to_resolution,
        "score": round(calc_score(probability, volume, liquidity), 6),
    }


def adapt_polymarket_market(event, market, now_utc):
    question = safe_str(market.get("question"))
    slug = safe_str(market.get("slug"))
    event_title = safe_str(event.get("title")) or question

    probability = safe_float(
        market.get("probability"),
        safe_float(market.get("lastTradePrice"), 0.0)
    )
    volume = safe_float(market.get("volume"), 0.0)
    liquidity = safe_float(market.get("liquidity"), 0.0)

    if probability < PRICE_MIN or probability > PRICE_MAX:
        return None
    if volume < POLYMARKET_VOLUME_MIN:
        return None
    if liquidity < POLYMARKET_LIQUIDITY_MIN:
        return None

    resolution_dt = (
        parse_iso_datetime(market.get("endDate"))
        or parse_iso_datetime(event.get("endDate"))
        or parse_iso_datetime(market.get("resolveDate"))
        or parse_iso_datetime(event.get("resolveDate"))
    )

    platform_market_id = market.get("id") or slug or question

    return build_standard_record(
        source="polymarket",
        platform_market_id=platform_market_id,
        event_title=event_title,
        question=question,
        slug=slug,
        probability=probability,
        volume=volume,
        liquidity=liquidity,
        now_utc=now_utc,
        resolution_dt=resolution_dt,
    )


def build_polymarket_rows(events, now_utc):
    rows = []

    for ev in events:
        for market in (ev.get("markets") or []):
            item = adapt_polymarket_market(ev, market, now_utc)
            if item is not None:
                rows.append(item)

    return rows


def choose_kalshi_probability(raw_item):
    last_price = safe_float(raw_item.get("last_price_dollars"), 0.0)
    yes_bid = safe_float(raw_item.get("yes_bid_dollars"), 0.0)
    yes_ask = safe_float(raw_item.get("yes_ask_dollars"), 0.0)

    if last_price <= 0:
        raw_last = safe_float(raw_item.get("last_price"), 0.0)
        if raw_last > 1:
            last_price = raw_last / 100.0
        else:
            last_price = raw_last

    if yes_bid <= 0:
        raw_yes_bid = safe_float(raw_item.get("yes_bid"), 0.0)
        yes_bid = raw_yes_bid / 100.0 if raw_yes_bid > 1 else raw_yes_bid

    if yes_ask <= 0:
        raw_yes_ask = safe_float(raw_item.get("yes_ask"), 0.0)
        yes_ask = raw_yes_ask / 100.0 if raw_yes_ask > 1 else raw_yes_ask

    if last_price > 0:
        return last_price, last_price, yes_bid, yes_ask

    valid = [x for x in (yes_bid, yes_ask) if x > 0]
    if valid:
        midpoint = sum(valid) / len(valid)
        return midpoint, last_price, yes_bid, yes_ask

    return 0.0, last_price, yes_bid, yes_ask


def choose_kalshi_volume_liquidity(raw_item):
    volume = safe_float(raw_item.get("volume"), 0.0)
    liquidity = safe_float(raw_item.get("liquidity"), 0.0)

    if volume <= 0:
        volume = safe_float(raw_item.get("volume_dollars"), 0.0)
    if liquidity <= 0:
        liquidity = safe_float(raw_item.get("liquidity_dollars"), 0.0)

    return volume, liquidity


def kalshi_mode_allows_type(market_type):
    if KALSHI_MODE == "all":
        return True
    if KALSHI_MODE != "macro_politics":
        return True
    return market_type in KALSHI_ALLOWED_TYPES


def adapt_kalshi_market(raw_item, now_utc):
    status = safe_str(raw_item.get("status")).lower()
    if status in ("closed", "settled", "finalized"):
        return None

    probability, _, _, _ = choose_kalshi_probability(raw_item)
    volume, liquidity = choose_kalshi_volume_liquidity(raw_item)

    if probability < PRICE_MIN or probability > PRICE_MAX:
        return None
    if volume < KALSHI_VOLUME_MIN:
        return None
    if liquidity < KALSHI_LIQUIDITY_MIN:
        return None

    question = safe_str(raw_item.get("title"))
    event_title = safe_str(raw_item.get("event_ticker")) or question
    slug = safe_str(raw_item.get("ticker")).lower()

    market_type = detect_market_type(event_title, question)
    if not kalshi_mode_allows_type(market_type):
        return None

    platform_market_id = raw_item.get("ticker") or slug
    resolution_dt = (
        parse_iso_datetime(raw_item.get("expiration_time"))
        or parse_iso_datetime(raw_item.get("latest_expiration_time"))
        or parse_iso_datetime(raw_item.get("close_time"))
    )

    return build_standard_record(
        source="kalshi",
        platform_market_id=platform_market_id,
        event_title=event_title,
        question=question,
        slug=slug,
        probability=probability,
        volume=volume,
        liquidity=liquidity,
        now_utc=now_utc,
        resolution_dt=resolution_dt,
    )


def build_kalshi_rows(markets, now_utc):
    rows = []

    total_markets = 0
    bad_status = 0
    bad_probability = 0
    bad_volume = 0
    bad_liquidity = 0
    bad_category = 0
    passed = 0
    status_counts = {}

    for item in markets:
        total_markets += 1

        status = safe_str(item.get("status")).lower()
        status_counts[status] = status_counts.get(status, 0) + 1

        if status in ("closed", "settled", "finalized"):
            bad_status += 1
            continue

        probability, _, _, _ = choose_kalshi_probability(item)
        volume, liquidity = choose_kalshi_volume_liquidity(item)

        event_title = safe_str(item.get("event_ticker")) or safe_str(item.get("title"))
        question = safe_str(item.get("title"))
        guessed_type = detect_market_type(event_title, question)

        if probability < PRICE_MIN or probability > PRICE_MAX:
            bad_probability += 1
            continue

        if volume < KALSHI_VOLUME_MIN:
            bad_volume += 1
            continue

        if liquidity < KALSHI_LIQUIDITY_MIN:
            bad_liquidity += 1
            continue

        if not kalshi_mode_allows_type(guessed_type):
            bad_category += 1
            continue

        record = adapt_kalshi_market(item, now_utc)
        if record is not None:
            rows.append(record)
            passed += 1

    debug_print("KALSHI_MODE:", KALSHI_MODE)
    debug_print("KALSHI_STATUS_COUNTS:", status_counts)
    debug_print("KALSHI_TOTAL_MARKETS:", total_markets)
    debug_print("KALSHI_BAD_STATUS:", bad_status)
    debug_print("KALSHI_BAD_PROBABILITY:", bad_probability)
    debug_print("KALSHI_BAD_VOLUME:", bad_volume)
    debug_print("KALSHI_BAD_LIQUIDITY:", bad_liquidity)
    debug_print("KALSHI_BAD_CATEGORY:", bad_category)
    debug_print("KALSHI_PASSED:", passed)

    return rows


def fetch_kalshi_series_tickers():
    tickers = []
    seen = set()

    for category in KALSHI_SERIES_CATEGORIES:
        params = {
            "category": category,
            "limit": 200,
        }

        resp = requests.get(KALSHI_SERIES_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        series_list = data.get("series") or []
        if not isinstance(series_list, list):
            debug_print("KALSHI_SERIES_BAD_PAYLOAD:", category, type(series_list).__name__)
            series_list = []

        debug_print("KALSHI_SERIES_CATEGORY:", category)
        debug_print("KALSHI_SERIES_FOUND:", len(series_list))

        for item in series_list:
            ticker = safe_str(item.get("ticker")).strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            tickers.append(ticker)

    if not tickers:
        debug_print("KALSHI_SERIES_FALLBACK_USED:", True)
        debug_print("KALSHI_SERIES_TOTAL_UNIQUE:", len(KALSHI_FALLBACK_SERIES_ALLOWLIST))
        return list(KALSHI_FALLBACK_SERIES_ALLOWLIST)

    debug_print("KALSHI_SERIES_FALLBACK_USED:", False)
    debug_print("KALSHI_SERIES_TOTAL_UNIQUE:", len(tickers))
    return tickers


def series_has_open_markets(series_ticker):
    params = dict(KALSHI_MARKETS_PARAMS)
    params["series_ticker"] = series_ticker
    params["limit"] = 1

    resp = requests.get(KALSHI_MARKETS_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    markets = data.get("markets", [])
    if not isinstance(markets, list):
        raise ValueError("Kalshi API response markets field is not a list")

    has_open = len(markets) > 0
    debug_print("KALSHI_SERIES_CHECK:", series_ticker)
    debug_print("KALSHI_SERIES_HAS_OPEN:", has_open)
    return has_open


def filter_series_with_open_markets(series_tickers):
    valid = []

    for series_ticker in series_tickers:
        try:
            if series_has_open_markets(series_ticker):
                valid.append(series_ticker)
        except Exception as e:
            debug_print("KALSHI_SERIES_CHECK_ERROR:", series_ticker, safe_str(e))

    debug_print("KALSHI_SERIES_VALIDATED_COUNT:", len(valid))
    return valid


def fetch_polymarket_rows(now_utc):
    resp = requests.get(POLYMARKET_BASE_URL, params=POLYMARKET_PARAMS, timeout=TIMEOUT)
    resp.raise_for_status()
    events = resp.json()

    if not isinstance(events, list):
        raise ValueError("Polymarket API response is not a list")

    return build_polymarket_rows(events, now_utc)


def fetch_kalshi_rows(now_utc):
    rows = []
    series_tickers = fetch_kalshi_series_tickers()
    series_tickers = filter_series_with_open_markets(series_tickers)

    for series_ticker in series_tickers:
        cursor = None
        page_count = 0

        while page_count < KALSHI_MAX_PAGES:
            params = dict(KALSHI_MARKETS_PARAMS)
            params["series_ticker"] = series_ticker
            if cursor:
                params["cursor"] = cursor

            resp = requests.get(KALSHI_MARKETS_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            markets = data.get("markets", [])
            if not isinstance(markets, list):
                raise ValueError("Kalshi API response markets field is not a list")

            page_rows = build_kalshi_rows(markets, now_utc)
            rows.extend(page_rows)

            page_count += 1
            cursor = data.get("cursor")

            debug_print("KALSHI_SERIES:", series_ticker)
            debug_print("KALSHI_PAGE:", page_count)
            debug_print("KALSHI_PAGE_ROWS:", len(page_rows))
            debug_print("KALSHI_TOTAL_ACCUMULATED:", len(rows))

            if not cursor:
                break

    return rows


def dedupe_rows(rows):
    deduped = []
    seen = set()

    for item in rows:
        key = (item.get("source"), item.get("platform_market_id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts = now_utc.strftime("%Y-%m-%d_%H-%M")

    timestamped_csv = os.path.join(base_dir, f"polymarket_focus_{ts}.csv")
    timestamped_json = os.path.join(base_dir, f"polymarket_focus_{ts}.json")
    latest_csv = os.path.join(base_dir, "polymarket_focus_latest.csv")
    latest_json = os.path.join(base_dir, "polymarket_focus_latest.json")

    header = [
        "schema_version",
        "source",
        "platform_market_id",
        "market_type",
        "event",
        "question",
        "slug",
        "probability",
        "volume",
        "liquidity",
        "timestamp",
        "resolution_time",
        "hours_to_resolution",
        "score",
    ]

    json_rows = []

    if ENABLE_POLYMARKET:
        json_rows.extend(fetch_polymarket_rows(now_utc))

    if ENABLE_KALSHI:
        json_rows.extend(fetch_kalshi_rows(now_utc))

    json_rows = dedupe_rows(json_rows)
    json_rows.sort(
        key=lambda x: (
            -x["score"],
            x["source"],
            x["platform_market_id"],
        )
    )

    csv_rows = [
        [
            item["schema_version"],
            item["source"],
            item["platform_market_id"],
            item["market_type"],
            item["event"],
            item["question"],
            item["slug"],
            item["probability"],
            item["volume"],
            item["liquidity"],
            item["timestamp"],
            item["resolution_time"],
            item["hours_to_resolution"],
            item["score"],
        ]
        for item in json_rows
    ]

    write_csv_atomic(timestamped_csv, header, csv_rows)
    write_json_atomic(timestamped_json, json_rows)
    refresh_latest_file(timestamped_csv, latest_csv)
    refresh_latest_file(timestamped_json, latest_json)
    cleanup_old_exports(base_dir, KEEP_LATEST_COUNT)

    print("EXPORT_OK:", True, flush=True)
    print("ROWS_TOTAL:", len(json_rows), flush=True)
    print("CSV_FILE:", os.path.basename(timestamped_csv), flush=True)
    print("JSON_FILE:", os.path.basename(timestamped_json), flush=True)
    print("LATEST_CSV_FILE:", os.path.basename(latest_csv), flush=True)
    print("LATEST_JSON_FILE:", os.path.basename(latest_json), flush=True)
    print("ENABLE_POLYMARKET:", ENABLE_POLYMARKET, flush=True)
    print("ENABLE_KALSHI:", ENABLE_KALSHI, flush=True)
    print("KALSHI_MODE:", KALSHI_MODE, flush=True)
    print("DEBUG:", DEBUG, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
