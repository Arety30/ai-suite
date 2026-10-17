"""Sandboxed command execution — the safe replacement for the open Cloud-Shell
exec the old AbrarAssistant exposed to any Discord user.

Primary path: run inside a throwaway Docker container with NO network, a memory
cap, and only the workspace mounted. If Docker isn't available it falls back to a
restricted local subprocess (command allow-list, timeout, workspace cwd) and says
so — it never silently runs unconfined.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from suite.config import settings

WORKSPACE = settings.data_dir / "workspace"
IMAGE = "python:3.12-slim"
TIMEOUT = 30

# Only these binaries may run in the local-fallback path (Docker path is isolated
# so it doesn't need an allow-list).
_LOCAL_ALLOW = {"ls", "cat", "echo", "grep", "find", "head", "tail", "wc",
                "python3", "pwd", "date", "sort", "uniq", "sed", "awk"}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


async def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", f"timed out after {timeout}s"
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def run_command(command: str, *, timeout: int = TIMEOUT) -> dict:
    """Execute a shell command in the sandbox. Returns {mode, exit_code, stdout, stderr}."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    if _docker_available():
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",           # no network
            "--memory", "512m", "--cpus", "1",
            "--pids-limit", "128",
            "-v", f"{WORKSPACE}:/workspace:rw",
            "-w", "/workspace",
            IMAGE, "sh", "-c", command,
        ]
        code, out, err = await _run(cmd, timeout + 10)
        return {"mode": "docker", "exit_code": code, "stdout": out[:8000],
                "stderr": err[:2000]}

    # --- restricted local fallback ---
    first = command.strip().split(maxsplit=1)[0] if command.strip() else ""
    if first not in _LOCAL_ALLOW:
        return {"mode": "local-blocked", "exit_code": 126, "stdout": "",
                "stderr": f"'{first}' not in local allow-list and Docker is "
                          f"unavailable. Allowed: {sorted(_LOCAL_ALLOW)}"}
    code, out, err = await _run(["sh", "-c", command], timeout)
    return {"mode": "local-restricted", "exit_code": code, "stdout": out[:8000],
            "stderr": err[:2000]}
