"""Outbound events — the hub calls configured n8n (or any) webhook URLs when
something happens, so local automations can react.

Complements the inbound Flows API (n8n -> hub). Configure under [n8n] in
config.toml; disabled by default. Emitting never raises into the caller — a dead
webhook is logged in the return value, not propagated.
"""
from __future__ import annotations

import httpx

from suite.config import settings


def _config() -> dict:
    return settings.raw.get("n8n", {})


def webhooks_for(event: str) -> list[str]:
    """URLs subscribed to this event (or to '*' for all events)."""
    cfg = _config()
    if not cfg.get("enabled"):
        return []
    return [h["url"] for h in cfg.get("webhooks", [])
            if h.get("url") and h.get("event") in (event, "*")]


async def emit(event: str, payload: dict) -> list[dict]:
    """POST {event, data} to every subscribed webhook. Returns per-URL results."""
    results = []
    for url in webhooks_for(event):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(url, json={"event": event, "data": payload})
            results.append({"url": url, "status": r.status_code})
        except Exception as exc:  # noqa: BLE001 - a bad webhook must not break the hub
            results.append({"url": url, "error": str(exc)})
    return results
