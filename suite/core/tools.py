"""Local tools an agent can invoke via the ACTION protocol. All offline.

Consolidates OpenManus's system_tools.py (file_finder, resource_monitor) + the
sandboxed shell. Each tool is (name, description, coroutine(arg:str)->str) so the
agent loop can list them in the prompt and dispatch by name.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from suite.config import settings
from suite.core import sandbox

WORKSPACE = settings.data_dir / "workspace"


async def _file_finder(arg: str) -> str:
    """arg: '<pattern> [start_dir]'. Finds files by name under the workspace."""
    parts = shlex.split(arg) if arg else []
    pattern = parts[0] if parts else "*"
    start = Path(parts[1]) if len(parts) > 1 else WORKSPACE
    if not str(start).startswith(str(WORKSPACE)):
        start = WORKSPACE  # keep it inside the workspace
    hits = [str(p) for p in start.rglob(pattern)][:50]
    return "\n".join(hits) if hits else f"no files matching {pattern!r}"


async def _resource_monitor(arg: str) -> str:
    """Local CPU / memory / disk snapshot via psutil."""
    try:
        import psutil
    except ImportError:
        return "psutil not installed"
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return (f"cpu={psutil.cpu_percent(interval=0.3)}% "
            f"mem={vm.percent}% ({vm.used // 2**20}/{vm.total // 2**20} MB) "
            f"disk={du.percent}% ({du.used // 2**30}/{du.total // 2**30} GB)")


async def _read_file(arg: str) -> str:
    path = (WORKSPACE / arg.strip()).resolve()
    if not str(path).startswith(str(WORKSPACE.resolve())):
        return "path escapes workspace"
    if not path.exists():
        return f"not found: {arg}"
    return path.read_text(errors="replace")[:8000]


async def _write_file(arg: str) -> str:
    """arg: '<relpath> :: <content>'."""
    if "::" not in arg:
        return "usage: WRITE_FILE <path> :: <content>"
    rel, content = arg.split("::", 1)
    path = (WORKSPACE / rel.strip()).resolve()
    if not str(path).startswith(str(WORKSPACE.resolve())):
        return "path escapes workspace"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip())
    return f"wrote {len(content.strip())} bytes to {rel.strip()}"


async def _shell(arg: str) -> str:
    result = await sandbox.run_command(arg)
    body = result["stdout"] or result["stderr"] or "(no output)"
    return f"[{result['mode']} exit={result['exit_code']}]\n{body}"


async def _map_search(arg: str) -> str:
    from suite.core import maps
    hits = maps.text_search(arg)
    if not hits and await maps.refresh(arg):
        hits = maps.text_search(arg)
    if not hits:
        return f"no cached places for {arg!r} (offline? try MAP_REFRESH when connected)"
    return "\n".join(f"{p['name']}" + (f" — {p['address']}" if p.get('address') else "")
                     + (f" ({p['lat']:.4f},{p['lng']:.4f})" if p.get('lat') else "") for p in hits[:20])


async def _map_refresh(arg: str) -> str:
    from suite.core import maps
    n = await maps.refresh(arg)
    return f"cached {n} place(s) for {arg!r}" if n else "couldn't fetch (offline or no API key)"


async def _map_near(arg: str) -> str:
    from suite.core import maps
    parts = arg.split()
    if len(parts) < 2:
        return "usage: MAP_NEAR <lat> <lng> [radius_km]"
    lat, lng = float(parts[0]), float(parts[1])
    radius = float(parts[2]) if len(parts) > 2 else 5.0
    rows = await maps.near(lat, lng, radius)
    return "\n".join(f"{r['name']} — {r['distance_km']} km" for r in rows) or f"none within {radius} km"


async def _geocode(arg: str) -> str:
    from suite.core import maps
    res = await maps.geocode(arg)
    return f"{res['formatted_address']} → {res['lat']:.5f},{res['lng']:.5f}" if res \
        else "not cached / offline / no API key"


# name -> (description, coroutine)
TOOLS: dict[str, tuple[str, object]] = {
    "SHELL": ("Run a shell command in an isolated sandbox. ARG: the command.", _shell),
    "FIND": ("Find files by name. ARG: '<pattern> [dir]'.", _file_finder),
    "RESOURCES": ("Report CPU/memory/disk usage. ARG: (none).", _resource_monitor),
    "READ_FILE": ("Read a workspace file. ARG: relative path.", _read_file),
    "WRITE_FILE": ("Write a workspace file. ARG: '<path> :: <content>'.", _write_file),
    "MAP_SEARCH": ("Search cached map places (offline). ARG: query e.g. 'cafes in Karachi'.", _map_search),
    "MAP_REFRESH": ("Fetch+cache map data (online). ARG: query.", _map_refresh),
    "MAP_NEAR": ("Nearest cached places to a point (C++ geo). ARG: '<lat> <lng> [radius_km]'.", _map_near),
    "GEOCODE": ("Address → coordinates. ARG: an address.", _geocode),
}


def tool_catalog() -> str:
    return "\n".join(f"  {name}: {desc}" for name, (desc, _) in TOOLS.items())


async def run_tool(name: str, arg: str) -> str:
    entry = TOOLS.get(name.upper())
    if not entry:
        return f"unknown tool {name!r}. Available: {', '.join(TOOLS)}"
    _desc, fn = entry
    try:
        return await fn(arg)
    except Exception as exc:  # noqa: BLE001 - tools must never crash the agent loop
        return f"tool {name} error: {exc}"
