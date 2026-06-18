from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import subprocess
import json

APP = FastAPI(title="Polymarket Agent Bridge", version="0.1.0")
ROOT = Path("/root/polymarket").resolve()
BLOCKED_MARKERS = [".env", ".git", "id_rsa", ".pem", "known_hosts"]
AUTO_ALLOWED_PREFIXES = (
    "python ",
    "python3 ",
    "pytest",
    "grep ",
    "cat ",
    "sed ",
    "awk ",
    "git diff",
    "git status",
    "git rev-parse",
)
APPROVAL_REQUIRED_PREFIXES = (
    "systemctl ",
    "service ",
    "pip ",
    "pip3 ",
    "apt ",
    "apt-get ",
    "rm ",
    "mv ",
    "cp ",
    "curl ",
    "wget ",
    "mysql ",
    "mariadb ",
)


def safe_path(p: str) -> Path:
    candidate = Path(p)
    full = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    if full != ROOT and ROOT not in full.parents:
        raise HTTPException(status_code=403, detail="path outside workspace")
    for marker in BLOCKED_MARKERS:
        if marker in str(full):
            raise HTTPException(status_code=403, detail=f"protected path: {marker}")
    return full


class ReadReq(BaseModel):
    path: str = Field(..., description="Path relative to /root/polymarket or absolute within it")
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


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


class ListReq(BaseModel):
    path: str = "."


@APP.post("/list_dir")
def list_dir(req: ListReq):
    p = safe_path(req.path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")
    items = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        items.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "path": str(child),
        })
    return {"path": str(p), "items": items}


class ReplaceReq(BaseModel):
    path: str
    find: str
    replace: str
    expected_count: int = Field(default=1, ge=1)


@APP.post("/replace_in_file")
def replace_in_file(req: ReplaceReq):
    p = safe_path(req.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    text = p.read_text(encoding="utf-8")
    count = text.count(req.find)
    if count != req.expected_count:
        raise HTTPException(status_code=409, detail=f"expected {req.expected_count}, found {count}")
    updated = text.replace(req.find, req.replace)
    p.write_text(updated, encoding="utf-8")
    return {"ok": True, "path": str(p), "replacements": count}


class WriteReq(BaseModel):
    path: str
    content: str
    mode: str = Field(default="overwrite", pattern="^(overwrite|append|create)$")


@APP.post("/write_file")
def write_file(req: WriteReq):
    p = safe_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if req.mode == "create" and p.exists():
        raise HTTPException(status_code=409, detail="file already exists")
    if req.mode == "append":
        with p.open("a", encoding="utf-8") as f:
            f.write(req.content)
    else:
        p.write_text(req.content, encoding="utf-8")
    return {"ok": True, "path": str(p), "mode": req.mode, "bytes": len(req.content.encode("utf-8"))}


class CmdReq(BaseModel):
    cmd: str
    cwd: str = "."
    timeout_s: int = Field(default=30, ge=1, le=120)
    approved: bool = False


@APP.post("/run_command")
def run_command(req: CmdReq):
    cwd = safe_path(req.cwd)
    cmd = req.cmd.strip()

    auto_allowed = cmd.startswith(AUTO_ALLOWED_PREFIXES)
    approval_required = cmd.startswith(APPROVAL_REQUIRED_PREFIXES)

    if not auto_allowed:
        if approval_required and not req.approved:
            raise HTTPException(status_code=403, detail="approval required")
        if not approval_required:
            raise HTTPException(status_code=403, detail="command not allowed")

    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=req.timeout_s,
    )
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "returncode": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
    }


@APP.get("/git_diff")
def git_diff():
    result = subprocess.run(
        "git diff -- /root/polymarket",
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


@APP.get("/health")
def health():
    return {
        "ok": True,
        "root": str(ROOT),
        "auto_allowed_prefixes": list(AUTO_ALLOWED_PREFIXES),
        "approval_required_prefixes": list(APPROVAL_REQUIRED_PREFIXES),
    }


TOOL_SCHEMAS = {
    "tools": [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a text file in /root/polymarket, optionally by line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": ["integer", "null"]},
                    "end_line": {"type": ["integer", "null"]}
                },
                "required": ["path"],
                "additionalProperties": False
            }
        },
        {
            "type": "function",
            "name": "replace_in_file",
            "description": "Replace an exact snippet in a file under /root/polymarket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                    "expected_count": {"type": "integer", "minimum": 1}
                },
                "required": ["path", "find", "replace"],
                "additionalProperties": False
            }
        },
        {
            "type": "function",
            "name": "run_command",
            "description": "Run an allowed shell command in /root/polymarket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout_s": {"type": "integer", "minimum": 1, "maximum": 120},
                    "approved": {"type": "boolean"}
                },
                "required": ["cmd"],
                "additionalProperties": False
            }
        }
    ]
}


if __name__ == "__main__":
    print(json.dumps(TOOL_SCHEMAS, indent=2))
