"""System — the machine room. Manage local Ollama models and read live resource
usage. All local: talks to the Ollama daemon on localhost and reads psutil.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/v1/system", tags=["system"])
OLLAMA = "http://localhost:11434"


@router.get("/models")
async def models():
    """List installed Ollama models."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{OLLAMA}/api/tags")
        r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        d = m.get("details", {})
        out.append({"name": m["name"], "size": m.get("size"),
                    "family": d.get("family"), "params": d.get("parameter_size")})
    return out


class ModelIn(BaseModel):
    name: str


@router.post("/models/pull")
async def pull(body: ModelIn):
    """Download a model (blocks until complete — can be slow for large models)."""
    async with httpx.AsyncClient(timeout=None) as c:
        r = await c.post(f"{OLLAMA}/api/pull",
                         json={"model": body.name, "name": body.name, "stream": False})
    ok = r.status_code == 200
    return {"name": body.name, "status": r.json().get("status", "done") if ok else "error"}


@router.delete("/models/{name}")
async def remove(name: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request("DELETE", f"{OLLAMA}/api/delete",
                            json={"model": name, "name": name})
    return {"name": name, "deleted": r.status_code == 200}


@router.get("/resources")
async def resources():
    """Live CPU / memory / disk snapshot (the Nexus status panel's data)."""
    import psutil
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory": {"percent": vm.percent, "used_mb": vm.used // 2**20,
                   "total_mb": vm.total // 2**20},
        "disk": {"percent": du.percent, "used_gb": du.used // 2**30,
                 "total_gb": du.total // 2**30},
    }
