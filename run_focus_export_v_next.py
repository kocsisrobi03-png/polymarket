import csv
import datetime
import glob
import json
import os
import shutil
import sys
import tempfile

import requests


SCHEMA_VERSION = "v5.1"

DEBUG = False

ENABLE_POLYMARKET = True
ENABLE_KALSHI = True

KALSHI_MODE = "macro_politics"
KALSHI_ALLOWED_TYPES = {"politics", "macro"}
KALSHI_SERIES_ALLOWLIST = {
    # politics
    "KXUSPRES",
    "KXUSSENATE",
    "KXUSHOUSE",
    "KXUSGOV",
    "KXUSPOLY",
    "KXCONGRESS",

    # macro / economics / rates / inflation
    "KXINFLATION",
    "KXFED",
    "KXFFR",
    "KXGDP",
    "KXJOBS",
    "KXUNEMP",
    "KXHOUSING",
    "KXOIL",
    "KXFX",
}
POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com/events"
POLYMARKET_PARAMS = {
    "active": "true",
    "closed": "false",
    "limit": 50,
    "order": "volume",
    "ascending": "false",
}

KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2/markets"
KALSHI_PARAMS = {
    "status": "open",
    "limit": 100,
    "mve_filter": "exclude",
}

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
            if name in ("polymarket_focus_latest.csv", "polymarket_focus_latest.json"):
                continue
            if os.path.isfile(path):
                files.append(path)

        files.sort(key=os.path.getmtime, reverse=True)

        for old_path in files[keep_count:]:
            os.remove(old_path)
            deleted.append(os.path.basename(old_path))

    return deleted


def normalize_text(*parts):
    return " ".join((p or "").strip() for p in parts).lower()


def detect_market_type(event_text, question_text):
    text = normalize_text(event_text, question_text)

    politics_keywords = [
        "trump", "election", "president", "presidential", "senate", "house",
        "vote", "white house", "democrat", "republican", "nominee", "governor",
        "prime minister", "parliament", "congress", "campaign",
        "iran", "israel", "ukraine", "russia", "china", "taiwan",
        "peace deal", "ceasefire", "war", "treaty", "sanctions", "nato",
        "putin", "zelensky", "netanyahu", "hungary", "orban", "poland",
        "germany", "france", "canada", "uk", "britain", "eu", "european union"
    ]
    macro_keywords = [
        "fed", "inflation", "rate", "recession", "gdp", "cpi", "tariff",
        "economy", "unemployment", "interest rate", "fomc", "oil", "gold",
        "treasury", "yield", "stock market", "s&p", "nasdaq", "dow", "brent",
        "wti", "usd", "dollar", "euro", "bank of england", "ecb"
    ]
    crypto_keywords = [
        "bitcoin", "btc", "eth", "ethereum", "crypto", "solana", "doge",
        "xrp", "token"
    ]
    sports_keywords = [
        "nba", "nfl", "mlb", "nhl", "f1", "formula 1", "soccer", "football",
        "championship", "super bowl", "world cup", "tennis", "drivers' champion",
        "grand prix", "playoffs", "ufc", "golf", "premier league",
        "manchester city", "arsenal", "liverpool", "chelsea",
        "mma", "fight", "hits", "runs", "rbis", "bases", "win the",
        "touchdown", "strikeout", "points scored", "assist", "rebounds"
    ]

    if any(k in text for k in politics_keywords):
        return "politics"
    if any(k in text for k in macro_keywords):
        return "macro"
    if any(k in text for k in crypto_keywords):
        return "crypto"
    if any(k in text for k in sports_keywords):
        return "sports"
    return "other"


def parse_resolution_time(event_obj, market_obj):
    candidates = [
        market_obj.get("endDate"),
        market_obj.get("end_date"),
        market_obj.get("resolutionDate"),
        market_obj.get("resolution_date"),
        event_obj.get("endDate"),
        event_obj.get("end_date"),
        event_obj.get("resolutionDate"),
        event_obj.get("resolution_date"),
    ]

    for value in candidates:
        dt = parse_iso_datetime(value)
        if dt is not None:
            return dt

    return None


def calc_score(probability, volume, liquidity):
    probability_balance = 1 - abs(probability - 0.275) / 0.125
    probability_balance = max(0, min(1, probability_balance))

    volume_score = min(volume / 500000, 1)
    liquidity_score = min(liquidity / 50000, 1)

    return round(
        0.5 * probability_balance +
        0.3 * volume_score +
        0.2 * liquidity_score,
        4
    )


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
    if resolution_dt is not None:
        resolution_time = resolution_dt.isoformat()
        hours_to_resolution = round((resolution_dt - now_utc).total_seconds() / 3600, 2)
    else:
        resolution_time = None
        hours_to_resolution = None

    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "platform_market_id": safe_str(platform_market_id),
        "market_type": detect_market_type(event_title, question),
        "event": event_title,
        "question": question,
        "slug": slug,
        "probability": probability,
        "volume": volume,
        "liquidity": liquidity,
        "timestamp": now_utc.isoformat(),
        "resolution_time": resolution_time,
        "hours_to_resolution": hours_to_resolution,
        "score": calc_score(probability, volume, liquidity),
    }


def kalshi_mode_allows_type(market_type, raw_item=None):
    if KALSHI_MODE == "all":
        return True

    if KALSHI_MODE != "macro_politics":
        return True

    raw_item = raw_item or {}
    category = normalize_text(safe_str(raw_item.get("category")))

    tags = raw_item.get("tags") or []
    normalized_tags = {
        normalize_text(safe_str(tag))
        for tag in tags
        if safe_str(tag).strip()
    }

    allowed_categories = {
        "politics",
        "elections",
        "economics",
        "financials",
    }

    blocked_categories = {
        "sports",
        "entertainment",
        "crypto",
        "climate and weather",
        "science and technology",
        "social",
        "companies",
        "commodities",
    }

    allowed_tags = {
        "trump",
        "congress",
        "international",
        "iran",
        "us elections",
        "primaries",
        "international elections",
        "house",
        "senate",
        "governor",
        "growth",
        "inflation",
        "jobs & economy",
        "oil and energy",
        "fed",
        "gdp",
        "global central banks",
        "housing",
        "econ daily",
        "indices",
        "foreign exchange",
        "interest rates",
        "politicians",
    }

    blocked_tags = {
        "soccer",
        "basketball",
        "baseball",
        "football",
        "golf",
        "hockey",
        "tennis",
        "mma",
        "esports",
        "boxing",
        "motorsport",
        "cricket",
        "chess",
        "btc",
        "eth",
        "sol",
        "doge",
        "xrp",
        "hourly",
        "15 min",
        "music",
        "awards",
        "movies",
        "television",
        "video games",
    }

    if category in blocked_categories:
        return False

    if normalized_tags & blocked_tags:
        return False

    if category in allowed_categories:
        return True

    if normalized_tags & allowed_tags:
        return True

    return market_type in KALSHI_ALLOWED_TYPES

def adapt_polymarket_market(event_obj, market_obj, now_utc):
    prices = parse_prices(market_obj.get("outcomePrices"))

    if not (
        market_obj.get("active", False)
        and not market_obj.get("closed", True)
        and market_obj.get("acceptingOrders", False)
        and isinstance(prices, list)
        and len(prices) == 2
    ):
        return None

    probability = safe_float(prices[0], -1)
    volume = safe_float(market_obj.get("volume"), 0)
    liquidity = safe_float(market_obj.get("liquidity"), 0)

    if probability < PRICE_MIN or probability > PRICE_MAX:
        return None
    if volume < POLYMARKET_VOLUME_MIN:
        return None
    if liquidity < POLYMARKET_LIQUIDITY_MIN:
        return None

    event_title = safe_str(event_obj.get("title"))
    question = safe_str(market_obj.get("question"))
    slug = safe_str(market_obj.get("slug"))

    platform_market_id = (
        market_obj.get("id")
        or market_obj.get("conditionId")
        or market_obj.get("questionID")
        or slug
    )

    resolution_dt = parse_resolution_time(event_obj, market_obj)

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


def choose_kalshi_probability(raw_item):
    last_price = safe_float(raw_item.get("last_price_dollars"), -1)
    yes_bid = safe_float(raw_item.get("yes_bid_dollars"), -1)
    yes_ask = safe_float(raw_item.get("yes_ask_dollars"), -1)

    probability = -1

    if PRICE_MIN <= last_price <= PRICE_MAX:
        probability = last_price
    elif 0 <= yes_bid <= 1 and 0 <= yes_ask <= 1 and yes_ask > 0:
        midpoint = round((yes_bid + yes_ask) / 2, 4)
        probability = midpoint
    elif PRICE_MIN <= yes_ask <= PRICE_MAX:
        probability = yes_ask
    elif PRICE_MIN <= yes_bid <= PRICE_MAX:
        probability = yes_bid

    return probability, last_price, yes_bid, yes_ask


def choose_kalshi_volume_liquidity(raw_item):
    volume = safe_float(raw_item.get("volume"), 0)
    if volume <= 0:
        volume = safe_float(raw_item.get("volume_fp"), 0)

    liquidity = safe_float(raw_item.get("liquidity"), 0)
    if liquidity <= 0:
        liquidity = safe_float(raw_item.get("liquidity_dollars"), 0)

    return volume, liquidity


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
    if not kalshi_mode_allows_type(market_type, raw_item):
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


def build_polymarket_rows(events, now_utc):
    rows = []

    for ev in events:
        for market in (ev.get("markets") or []):
            item = adapt_polymarket_market(ev, market, now_utc)
            if item is not None:
                rows.append(item)

    return rows


def build_kalshi_rows(markets, now_utc):
    rows = []

    total_markets = 0
    bad_status = 0
    bad_probability = 0
    bad_volume = 0
    bad_liquidity = 0
    bad_category = 0
    passed = 0
    sample_printed = 0
    status_counts = {}

    for item in markets:
        total_markets += 1

        status = safe_str(item.get("status")).lower()
        status_counts[status] = status_counts.get(status, 0) + 1

        if status in ("closed", "settled", "finalized"):
            bad_status += 1
            continue

        probability, last_price, yes_bid, yes_ask = choose_kalshi_probability(item)
        volume, liquidity = choose_kalshi_volume_liquidity(item)

        event_title = safe_str(item.get("event_ticker")) or safe_str(item.get("title"))
        question = safe_str(item.get("title"))
        guessed_type = detect_market_type(event_title, question)

        if DEBUG and sample_printed < 5:
            print(
                "KALSHI_SAMPLE:",
                {
                    "ticker": item.get("ticker"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "event_ticker": item.get("event_ticker"),
                    "last_price_dollars": last_price,
                    "yes_bid_dollars": yes_bid,
                    "yes_ask_dollars": yes_ask,
                    "volume_fp": item.get("volume_fp"),
                    "liquidity_dollars": item.get("liquidity_dollars"),
                    "volume": item.get("volume"),
                    "liquidity": item.get("liquidity"),
                    "response_price_units": item.get("response_price_units"),
                    "market_type": item.get("market_type"),
                    "guessed_type": guessed_type,
                    "parsed_probability": probability,
                },
                flush=True
            )
            sample_printed += 1

        if probability < PRICE_MIN or probability > PRICE_MAX:
            bad_probability += 1
            continue

        if volume < KALSHI_VOLUME_MIN:
            bad_volume += 1
            continue

        if liquidity < KALSHI_LIQUIDITY_MIN:
            bad_liquidity += 1
            continue

        if not kalshi_mode_allows_type(guessed_type, item):
            bad_category += 1
            continue

        record = adapt_kalshi_market(item, now_utc)
        if record is not None:
            rows.append(record)
            passed += 1

    print("KALSHI_MODE:", KALSHI_MODE, flush=True)
    print("KALSHI_STATUS_COUNTS:", status_counts, flush=True)
    print("KALSHI_TOTAL_MARKETS:", total_markets, flush=True)
    print("KALSHI_BAD_STATUS:", bad_status, flush=True)
    print("KALSHI_BAD_PROBABILITY:", bad_probability, flush=True)
    print("KALSHI_BAD_VOLUME:", bad_volume, flush=True)
    print("KALSHI_BAD_LIQUIDITY:", bad_liquidity, flush=True)
    print("KALSHI_BAD_CATEGORY:", bad_category, flush=True)
    print("KALSHI_PASSED:", passed, flush=True)

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
            params = dict(KALSHI_PARAMS)
            params["series_ticker"] = series_ticker
            if cursor:
                params["cursor"] = cursor

            resp = requests.get(KALSHI_BASE_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            markets = data.get("markets", [])
            if not isinstance(markets, list):
                raise ValueError("Kalshi API response markets field is not a list")

            page_rows = build_kalshi_rows(markets, now_utc)
            rows.extend(page_rows)

            page_count += 1
            cursor = data.get("cursor")

            print("KALSHI_SERIES:", series_ticker, flush=True)
            print("KALSHI_PAGE:", page_count, flush=True)
            print("KALSHI_PAGE_ROWS:", len(page_rows), flush=True)
            print("KALSHI_TOTAL_ACCUMULATED:", len(rows), flush=True)

            if not cursor:
                break

    return rows


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

    try:
        json_rows = []

        if ENABLE_POLYMARKET:
            json_rows.extend(fetch_polymarket_rows(now_utc))

        if ENABLE_KALSHI:
            json_rows.extend(fetch_kalshi_rows(now_utc))

        json_rows = dedupe_rows(json_rows)
        json_rows.sort(key=lambda x: x["score"], reverse=True)

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

        deleted_files = cleanup_old_exports(base_dir, KEEP_LATEST_COUNT)

        print("CSV_ROWS:", len(csv_rows))
        print("JSON_ROWS:", len(json_rows))
        print("CSV_FILE:", os.path.basename(timestamped_csv))
        print("JSON_FILE:", os.path.basename(timestamped_json))
        print("LATEST_CSV_FILE:", os.path.basename(latest_csv))
        print("LATEST_JSON_FILE:", os.path.basename(latest_json))
        print("DELETED_OLD_FILES:", len(deleted_files))
        print("ENABLE_POLYMARKET:", ENABLE_POLYMARKET)
        print("ENABLE_KALSHI:", ENABLE_KALSHI)
        print("KALSHI_MODE:", KALSHI_MODE)
        print("DEBUG:", DEBUG)
        return 0

    except requests.RequestException as e:
        print(f"ERROR: request failed: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        return 1
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

def series_has_open_markets(series_ticker):
    params = dict(KALSHI_PARAMS)
    params["series_ticker"] = series_ticker
    params["limit"] = 1

    resp = requests.get(KALSHI_BASE_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    markets = data.get("markets", [])
    if not isinstance(markets, list):
        raise ValueError("Kalshi API response markets field is not a list")

    has_open = len(markets) > 0
    print("KALSHI_SERIES_CHECK:", series_ticker, flush=True)
    print("KALSHI_SERIES_HAS_OPEN:", has_open, flush=True)
    return has_open


def filter_series_with_open_markets(series_tickers):
    valid = []

    for series_ticker in series_tickers:
        try:
            if series_has_open_markets(series_ticker):
                valid.append(series_ticker)
        except Exception as e:
            print("KALSHI_SERIES_CHECK_ERROR:", series_ticker, safe_str(e), flush=True)

    print("KALSHI_SERIES_VALIDATED_COUNT:", len(valid), flush=True)
    return valid
