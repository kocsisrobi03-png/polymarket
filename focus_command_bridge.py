
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pathlib import Path
import subprocess
import json

APP = FastAPI(title="Polymarket Focus Command Bridge", version="0.5.0")

ROOT = Path("/root/polymarket").resolve()
WRAPPER = ROOT / "focus_check_wrapper_smart.sh"
EXPORT_SCRIPT = ROOT / "run_focus_export_clean.py"
LATEST_JSON = ROOT / "polymarket_focus_latest.json"

class TickerReq(BaseModel):
    ticker: str

class SeriesReq(BaseModel):
    series: str

def ok_response(status: str, data=None, count=None, **extra):
    payload = {
        "ok": True,
        "status": status,
        "count": count,
        "data": data if data is not None else {},
    }
    payload.update(extra)
    return payload

def run_cmd(cmd: list[str], timeout: int = 180) -> dict:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
        "ok": result.returncode == 0,
        "status": "ok" if result.returncode == 0 else "error",
        "count": 0,
        "data": {
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-8000:],
        },
        "returncode": result.returncode,
    }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="command timeout")

def load_latest_json():
    if not LATEST_JSON.exists():
        raise HTTPException(status_code=404, detail="latest json not found")
    return json.loads(LATEST_JSON.read_text(encoding="utf-8"))

def normalize_market(item: dict) -> dict:
    return {
        "platform_market_id": item.get("platform_market_id"),
        "question": item.get("question"),
        "event": item.get("event"),
        "slug": item.get("slug"),
    }

@APP.get("/health")
def health():
    return ok_response(
        status="ready",
        count=0,
        data={
            "root": str(ROOT),
            "wrapper_exists": WRAPPER.exists(),
            "export_exists": EXPORT_SCRIPT.exists(),
            "latest_json_exists": LATEST_JSON.exists(),
        },
    )

@APP.post("/run_export")
def run_export():
    if not EXPORT_SCRIPT.exists():
        raise HTTPException(status_code=404, detail="export script not found")
    return run_cmd(["python3", str(EXPORT_SCRIPT)])

@APP.post("/check_ticker")
def check_ticker(req: TickerReq):
    if not WRAPPER.exists():
        raise HTTPException(status_code=404, detail="smart wrapper not found")
    return run_cmd(["bash", str(WRAPPER), req.ticker])

@APP.post("/run_export_and_check")
def run_export_and_check(req: TickerReq):
    if not WRAPPER.exists():
        raise HTTPException(status_code=404, detail="smart wrapper not found")
    return run_cmd(["bash", str(WRAPPER), req.ticker], timeout=240)

@APP.post("/check_series")
def check_series(req: SeriesReq):
    data = load_latest_json()
    prefix = req.series.strip().upper()
    matches = []

    for item in data if isinstance(data, list) else []:
        pmid = str(item.get("platform_market_id", ""))
        if pmid.upper().startswith(prefix):
            matches.append(normalize_market(item))

    return ok_response(
        status="filtered",
        count=len(matches),
        data={
            "series": prefix,
            "matches": matches[:50],
        },
    )

@APP.get("/latest_markets")
def latest_markets(
    series: str | None = Query(default=None),
    contains: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
):
    data = load_latest_json()
    rows = data if isinstance(data, list) else []

    prefix = None
    if series:
        prefix = series.strip().upper()
        rows = [
            item for item in rows
            if str(item.get("platform_market_id", "")).upper().startswith(prefix)
        ]

    contains_norm = None
    if contains:
        contains_norm = contains.strip().upper()
        rows = [
            item for item in rows
            if contains_norm in str(item.get("platform_market_id", "")).upper()
            or contains_norm in str(item.get("event", "")).upper()
            or contains_norm in str(item.get("slug", "")).upper()
            or contains_norm in str(item.get("question", "")).upper()
        ]

    markets = [normalize_market(item) for item in rows[:limit]]

    return ok_response(
        status="filtered",
        count=len(rows),
        data={
            "series": prefix,
            "contains": contains_norm,
            "limit": limit,
            "markets": markets,
        },
    )
@APP.get("/latest_ticker")
def latest_ticker(ticker: str = Query(..., min_length=1)):
    data = load_latest_json()
    target = ticker.strip().upper()

    for item in data if isinstance(data, list) else []:
        pmid = str(item.get("platform_market_id", "")).upper()
        if pmid == target:
            return ok_response(
                status="found",
                count=1,
                data={
                    "ticker": target,
                    "market": normalize_market(item),
                },
            )

    return ok_response(
        status="not_found",
        count=0,
        data={
            "ticker": target,
            "market": None,
        },
    )

@APP.get("/latest_summary")
def latest_summary():
    data = load_latest_json()
    rows = len(data) if isinstance(data, list) else 0
    series = {}

    for item in data if isinstance(data, list) else []:
        pmid = str(item.get("platform_market_id", ""))
        prefix = pmid.split("-")[0] if "-" in pmid else "UNKNOWN"
        series[prefix] = series.get(prefix, 0) + 1

    top_series = dict(sorted(series.items(), key=lambda kv: (-kv[1], kv[0]))[:10])

    return ok_response(
        status="summary",
        count=rows,
        data={
            "top_series": top_series,
            "file": str(LATEST_JSON),
        },
    )

