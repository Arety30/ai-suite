"""n8n outbound routes — inspect configured webhooks and fire a test event."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from suite.config import settings
from suite.core import events

router = APIRouter(prefix="/v1/n8n", tags=["n8n"])


@router.get("/webhooks")
async def webhooks():
    cfg = settings.raw.get("n8n", {})
    return {"enabled": bool(cfg.get("enabled")),
            "webhooks": cfg.get("webhooks", [])}


class TestIn(BaseModel):
    event: str = "test"
    data: dict | None = None


@router.post("/test")
async def test(body: TestIn):
    """Fire an event to its subscribed webhooks and report the delivery results."""
    results = await events.emit(body.event, body.data or {"hello": "from Abrar AI Hub"})
    return {"event": body.event, "delivered_to": len(results), "results": results}
