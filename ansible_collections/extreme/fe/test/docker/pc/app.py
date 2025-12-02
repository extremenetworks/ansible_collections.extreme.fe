# app.py
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, conlist
from typing import List, Optional, Dict
import os, subprocess, time, resource, shlex

app = FastAPI(
    title="Bash Runner",
    description="Single endpoint to run a list of Bash commands and return outputs.",
    version="1.0.0",
)

# --------- Models ---------
class RunRequest(BaseModel):
    commands: conlist(str, min_items=1, max_items=50) = Field(
        ..., description="List of commands to run in Bash (each as a single string)."
    )
    timeout_sec: int = Field(120, ge=1, le=120, description="Per-command wall clock timeout.")
    working_dir: Optional[str] = Field(None, description="Optional working directory for commands.")
    env: Optional[Dict[str, str]] = Field(None, description="Optional environment overrides.")
    # Optional allowlist (top-level command names). Omit or empty = no allowlist.
    allow: Optional[List[str]] = Field(None, description="Allowed top-level commands, e.g., ['echo','ls','uname'].")

class CommandResult(BaseModel):
    command: str
    returncode: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    truncated: bool

class RunResponse(BaseModel):
    results: List[CommandResult]
    all_ok: bool

# --------- Helpers ---------
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_BYTES", str(10 * 1024 * 1024)))  # 10 MB per stream
MEM_LIMIT_MB = int(os.getenv("MEM_LIMIT_MB", "1024"))                          # 1 GB address space limit
CPU_SOFT_LIMIT_SEC = int(os.getenv("CPU_SOFT_LIMIT_SEC", "120"))  # CPU time limit

def _truncate(s: str, limit: int) -> (str, bool):
    b = s.encode(errors="replace")
    if len(b) <= limit:
        return s, False
    # cut by bytes, not chars
    cut = b[:limit]
    return cut.decode(errors="ignore") + "\n[...truncated...]", True

def _set_rlimits():
    # CPU time (seconds of CPU, not wall clock)
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SOFT_LIMIT_SEC, CPU_SOFT_LIMIT_SEC))
    # Address space (bytes)
    bytes_limit = MEM_LIMIT_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
    # Prevent core dumps
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

def _top_level(cmd: str) -> str:
    # Best-effort: first token of the first pipeline
    first_segment = cmd.split("|", 1)[0]
    tokens = shlex.split(first_segment, posix=True) if first_segment.strip() else []
    return tokens[0] if tokens else ""

def _run_one(cmd: str, timeout_sec: int, cwd: Optional[str], env: Dict[str, str]) -> CommandResult:
    t0 = time.time()
    try:
        # run in bash so pipelines/redirections work
        full = f"set -o pipefail; {cmd}"
        proc = subprocess.run(
            ["/bin/bash", "-lc", full],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=timeout_sec,
            preexec_fn=_set_rlimits,
        )
        out, tout = _truncate(proc.stdout or "", MAX_OUTPUT_BYTES)
        err, terr = _truncate(proc.stderr or "", MAX_OUTPUT_BYTES)
        return CommandResult(
            command=cmd,
            returncode=proc.returncode,
            stdout=out,
            stderr=err,
            duration_ms=int((time.time() - t0) * 1000),
            timed_out=False,
            truncated=(tout or terr),
        )
    except subprocess.TimeoutExpired as e:
        # e.stdout / e.stderr may contain partial buffers
        out, tout = _truncate((e.stdout or ""), MAX_OUTPUT_BYTES)
        err, terr = _truncate((e.stderr or ""), MAX_OUTPUT_BYTES)
        return CommandResult(
            command=cmd,
            returncode=None,
            stdout=out,
            stderr=err + ("\n[TIMEOUT]" if not err.endswith("[TIMEOUT]") else ""),
            duration_ms=int((time.time() - t0) * 1000),
            timed_out=True,
            truncated=(tout or terr),
        )

# --------- Endpoint ---------
@app.post("/run", response_model=RunResponse, summary="Run a list of Bash commands")
async def run_commands(req: Request, body: RunRequest):
    # Simple API key gate (optional)
    expected_key = os.getenv("API_KEY", "")
    got_key = req.headers.get("x-api-key")
    if expected_key and got_key != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Optional allowlist
    if body.allow:
        disallowed = [c for c in body.commands if _top_level(c) not in set(body.allow)]
        if disallowed:
            raise HTTPException(
                status_code=400,
                detail=f"Disallowed commands present: {', '.join(sorted(set(_top_level(c) for c in disallowed)))}"
            )

    # Merge env safely
    env = os.environ.copy()
    if body.env:
        env.update({k: str(v) for k, v in body.env.items()})

    results = [
        _run_one(cmd, body.timeout_sec, body.working_dir, env)
        for cmd in body.commands
    ]
    all_ok = all((not r.timed_out) and (r.returncode == 0) for r in results)
    return RunResponse(results=results, all_ok=all_ok)
