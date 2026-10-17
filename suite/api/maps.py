"""Maps — offline map cache (ported from ai-hub). /v1/maps/*

Agents & adapters read cached places offline; refresh via API/scrape when online.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from suite.core import maps

router = APIRouter(prefix="/v1/maps", tags=["maps"])


@router.get("/search")
async def search(q: str):
    hits = maps.text_search(q)
    if not hits and await maps.refresh(q):
        hits = maps.text_search(q)
    return {"query": q, "count": len(hits), "places": hits}


class RefreshIn(BaseModel):
    query: str
    max_results: int = 20


@router.post("/refresh")
async def refresh(body: RefreshIn):
    n = await maps.refresh(body.query, body.max_results)
    return {"added": n, "total": maps.count() if hasattr(maps, "count") else len(maps.load())}


@router.get("/near")
async def near(lat: float, lng: float, radius_km: float = 5.0):
    return {"places": await maps.near(lat, lng, radius_km)}


@router.get("/geocode")
async def geocode(address: str):
    res = await maps.geocode(address)
    return res or {"error": "not cached / offline / no API key"}
