import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, Query
from pydantic import BaseModel

APP = FastAPI()

BASE_DIR = Path("/root/polymarket")
LATEST_JSON = BASE_DIR / "polymarket_focus_latest.json"


class TickerReq(BaseModel):
    ticker: str


class SeriesReq(BaseModel):
    series: str


def ok_response(status: str, data=None, count=None, **extra):
    payload = {
        "ok": True,
        "status": status,
    }
    if count is not None:
        payload["count"] = count
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def run_cmd(cmd: list[str], timeout: int = 180) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": cmd,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "cmd": cmd,
        }


def load_latest_json() -> list:
    if not LATEST_JSON.exists():
        return []
    try:
        raw = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def normalize_market(item: dict) -> dict:
    return {
        "platform_market_id": item.get("platform_market_id"),
        "question": item.get("question"),
        "event": item.get("event"),
        "slug": item.get("slug"),
    }


def market_platform(item: dict) -> str:
    return str(item.get("platform") or item.get("source") or "UNKNOWN")


def find_market_by_ticker(data: list, ticker: str):
    target = ticker.strip().upper()

    for item in data if isinstance(data, list) else []:
        pmid = str(item.get("platform_market_id", "")).upper()
        if pmid == target:
            return target, normalize_market(item)

    return target, None


def find_markets_by_series(data: list, series: str) -> tuple[str, list]:
    target = series.strip().upper()
    rows = []

    for item in data if isinstance(data, list) else []:
        event = str(item.get("event", "")).upper()
        pmid = str(item.get("platform_market_id", "")).upper()

        if event.startswith(target) or pmid.startswith(target):
            rows.append(normalize_market(item))

    return target, rows


@APP.get("/health")
def health():
    return ok_response(
        status="ok",
        data={
            "service": "polymarket-focus-bridge",
            "latest_json_exists": LATEST_JSON.exists(),
            "latest_json_file": str(LATEST_JSON),
        },
    )


@APP.post("/run_export")
def run_export():
    result = run_cmd(["/root/polymarket/.venv/bin/python", "run_focus_export_clean.py"])
    return ok_response(
        status="ok" if result["ok"] else "error",
        data={
            "export_ok": result["ok"],
            "export_returncode": result["returncode"],
            "export_stdout_tail": result["stdout"][-1200:],
            "export_stderr": result["stderr"],
        },
    )


@APP.post("/check_ticker")
def check_ticker(req: TickerReq):
    data = load_latest_json()
    target, market = find_market_by_ticker(data, req.ticker)

    return ok_response(
        status="found" if market else "not_found",
        count=1 if market else 0,
        data={
            "ticker": target,
            "latest_found": market is not None,
            "latest_market": market,
        },
    )


@APP.post("/run_export_and_check")
def run_export_and_check(req: TickerReq):
    export_result = run_cmd(["/root/polymarket/.venv/bin/python", "run_focus_export_clean.py"])

    data = load_latest_json()
    target, market = find_market_by_ticker(data, req.ticker)

    return ok_response(
        status="found" if market else "not_found",
        count=1 if market else 0,
        data={
            "ticker": target,
            "export_ok": export_result["ok"],
            "export_returncode": export_result["returncode"],
            "export_stdout_tail": export_result["stdout"][-1200:],
            "export_stderr": export_result["stderr"],
            "latest_found": market is not None,
            "latest_market": market,
        },
    )


@APP.post("/check_series")
def check_series(req: SeriesReq):
    data = load_latest_json()
    target, rows = find_markets_by_series(data, req.series)

    return ok_response(
        status="found" if rows else "not_found",
        count=len(rows),
        data={
            "series": target,
            "markets": rows,
        },
    )


@APP.get("/latest_markets")
def latest_markets(
    limit: int = Query(20, ge=1, le=500),
    event: str | None = None,
    platform: str | None = None,
):
    data = load_latest_json()
    rows = []

    for item in data if isinstance(data, list) else []:
        row = normalize_market(item)

        if event and str(row.get("event", "")).upper() != event.strip().upper():
            continue

        row_platform = market_platform(item).upper()
        if platform and row_platform != platform.strip().upper():
            continue

        rows.append(row)

    return ok_response(
        status="ok",
        count=len(rows[:limit]),
        data=rows[:limit],
    )


@APP.get("/latest_ticker")
def latest_ticker(ticker: str = Query(..., min_length=1)):
    data = load_latest_json()
    target, market = find_market_by_ticker(data, ticker)

    return ok_response(
        status="found" if market else "not_found",
        count=1 if market else 0,
        data={
            "ticker": target,
            "market": market,
        },
    )


@APP.get("/latest_series")
def latest_series(
    series: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
):
    data = load_latest_json()
    target, rows = find_markets_by_series(data, series)

    return ok_response(
        status="found" if rows else "not_found",
        count=len(rows),
        data={
            "series": target,
            "markets": rows[:limit],
        },
    )


@APP.get("/latest_summary")
def latest_summary():
    data = load_latest_json()
    rows = data if isinstance(data, list) else []

    by_event = {}
    by_platform = {}

    for item in rows:
        event = str(item.get("event", "") or "UNKNOWN")
        platform = market_platform(item)

        by_event[event] = by_event.get(event, 0) + 1
        by_platform[platform] = by_platform.get(platform, 0) + 1

    return ok_response(
        status="ok",
        data={
            "total_markets": len(rows),
            "by_event": by_event,
            "by_platform": by_platform,
        },
    )
