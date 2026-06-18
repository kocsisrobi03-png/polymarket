from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import difflib
import subprocess
import time

APP = FastAPI(title="Polymarket Agent Bridge Mini V2", version="0.2.1-mini")
ROOT = Path("/root/polymarket").resolve()
BLOCKED_MARKERS = [".env", ".git", "id_rsa", ".pem", "known_hosts"]
APPROVAL_QUEUE: dict[str, dict] = {}

def safe_path(p: str) -> Path:
    candidate = Path(p)
    full = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    if full != ROOT and ROOT not in full.parents:
        raise HTTPException(status_code=403, detail="path outside workspace")
    for marker in BLOCKED_MARKERS:
        if marker in str(full):
            raise HTTPException(status_code=403, detail=f"protected path: {marker}")
    return full

def make_diff(path: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
        )
    )

class ReadReq(BaseModel):
    path: str
    start_line: Optional[int] = Field(default=None, ge=1)
    end_line: Optional[int] = Field(default=None, ge=1)

@APP.get("/health")
def health():
    return {
        "ok": True,
        "version": "0.2.1-mini",
        "root": str(ROOT),
        "approval_queue_size": len(APPROVAL_QUEUE),
    }

@APP.post("/read_file")
def read_file(req: ReadReq):
    p = safe_path(req.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    lines = p.read_text(encoding="utf-8").splitlines()
    s = 0 if req.start_line is None else max(req.start_line - 1, 0)
    e = len(lines) if req.end_line is None else min(req.end_line, len(lines))
    return {
        "path": str(p),
        "start_line": s + 1,
        "end_line": e,
        "content": "\n".join(lines[s:e]),
    }

class PreviewReplaceReq(BaseModel):
    path: str
    find: str
    replace: str
    expected_count: int = Field(default=1, ge=1)

@APP.post("/preview_replace")
def preview_replace(req: PreviewReplaceReq):
    p = safe_path(req.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    old = p.read_text(encoding="utf-8")
    count = old.count(req.find)
    if count != req.expected_count:
        raise HTTPException(status_code=409, detail=f"expected {req.expected_count}, found {count}")
    new = old.replace(req.find, req.replace)
    diff = make_diff(str(p), old, new)
    approval_id = f"replace-{int(time.time() * 1000)}"
    APPROVAL_QUEUE[approval_id] = {
        "type": "replace_in_file",
        "path": str(p),
        "find": req.find,
        "replace": req.replace,
        "expected_count": req.expected_count,
        "diff": diff,
        "created_at": int(time.time()),
    }
    return {
        "approval_id": approval_id,
        "path": str(p),
        "replacements": count,
        "diff": diff,
    }

class ApplyApprovalReq(BaseModel):
    approval_id: str

@APP.post("/apply_approval")
def apply_approval(req: ApplyApprovalReq):
    item = APPROVAL_QUEUE.get(req.approval_id)
    if not item:
        raise HTTPException(status_code=404, detail="approval id not found")
    p = safe_path(item["path"])
    old = p.read_text(encoding="utf-8")
    count = old.count(item["find"])
    if count != item["expected_count"]:
        raise HTTPException(status_code=409, detail=f"expected {item['expected_count']}, found {count}")
    new = old.replace(item["find"], item["replace"])
    p.write_text(new, encoding="utf-8")
    APPROVAL_QUEUE.pop(req.approval_id, None)
    return {
        "ok": True,
        "type": "replace_in_file",
        "path": str(p),
        "replacements": count,
    }

@APP.get("/approvals")
def approvals():
    return {"items": APPROVAL_QUEUE}

@APP.get("/git_diff")
def git_diff():
    result = subprocess.run(
        "git diff -- .",
        cwd=str(ROOT),
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-8000:],
    }
