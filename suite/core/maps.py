"""Offline map cache — ported from ai-hub into the suite core.

Scrape/API-fetch map data when online, store it as local JSON, and let agents
query it offline. Fast spatial queries via the bundled C++ geo engine.
Pipeline: Google API / Playwright scrape (online) → JSON store → TSV → C++ geo.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from suite.config import settings

MAPS_DIR = settings.data_dir / "maps"
PLACES_JSON = MAPS_DIR / "places.json"
PLACES_TSV = MAPS_DIR / "places.tsv"
GEO_BIN = Path(__file__).parent / "maps_engine" / "geo_query"
MAPS_DIR.mkdir(parents=True, exist_ok=True)

_COORD = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
_TEXT = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def _key() -> str:
    return os.getenv("GOOGLE_MAPS_KEY", "")


async def is_online(timeout: float = 4.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            await c.head("https://maps.googleapis.com/")
        return True
    except Exception:
        return False


# ---- store -----------------------------------------------------------------
def load() -> list[dict]:
    if PLACES_JSON.exists():
        try:
            return json.loads(PLACES_JSON.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _pkey(p: dict) -> str:
    return p.get("place_id") or f"{p.get('name','').lower()}|{round(p.get('lat',0),5)},{round(p.get('lng',0),5)}"


def save(places: list[dict]) -> None:
    PLACES_JSON.write_text(json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    for i, p in enumerate(places):
        name = str(p.get("name", "")).replace("\t", " ")
        addr = str(p.get("address", "")).replace("\t", " ")
        lines.append(f"{i}\t{p.get('lat',0)}\t{p.get('lng',0)}\t{name}\t{addr}")
    PLACES_TSV.write_text("\n".join(lines), encoding="utf-8")


def upsert(new: list[dict]) -> int:
    places = load()
    idx = {_pkey(p): i for i, p in enumerate(places)}
    changed = 0
    for p in new:
        if not p.get("name"):
            continue
        p.setdefault("fetched_at", datetime.now().isoformat(timespec="seconds"))
        k = _pkey(p)
        if k in idx:
            places[idx[k]].update(p)
        else:
            idx[k] = len(places); places.append(p)
        changed += 1
    save(places)
    return changed


def text_search(query: str, limit: int = 25) -> list[dict]:
    q = (query or "").lower().strip()
    out = [p for p in load()
           if not q or all(w in f"{p.get('name','')} {p.get('address','')} {p.get('types','')}".lower()
                           for w in q.split())]
    return out[:limit]


# ---- online fetch ----------------------------------------------------------
def _norm(p: dict) -> dict:
    loc = (p.get("geometry", {}) or {}).get("location", {}) or {}
    return {"place_id": p.get("place_id", ""), "name": p.get("name", ""),
            "address": p.get("formatted_address") or p.get("vicinity", ""),
            "lat": loc.get("lat", 0.0), "lng": loc.get("lng", 0.0),
            "types": ",".join(p.get("types", []) or []),
            "rating": float(p.get("rating", 0) or 0), "source": "google"}


async def _api_text(query: str) -> list[dict]:
    if not _key():
        return []
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(_TEXT, params={"query": query, "key": _key()})
        return [_norm(p) for p in r.json().get("results", [])]
    except Exception:
        return []


async def _scrape(query: str, max_results: int = 20) -> list[dict]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return []
    url = f"https://www.google.com/maps/search/{quote_plus(query)}?hl=en"
    out = []
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            pg = await b.new_page(locale="en-US")
            await pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            for sel in ('button:has-text("Accept all")', 'button:has-text("Reject all")'):
                try:
                    if await pg.locator(sel).first.count():
                        await pg.locator(sel).first.click(timeout=3000); break
                except Exception:
                    pass
            try:
                await pg.wait_for_selector("a.hfpxzc", timeout=15000)
            except Exception:
                pass
            for _ in range(8):
                await pg.mouse.wheel(0, 3000); await pg.wait_for_timeout(900)
                if await pg.locator("a.hfpxzc").count() >= max_results:
                    break
            cards = pg.locator("a.hfpxzc")
            for i in range(min(await cards.count(), max_results)):
                a = cards.nth(i)
                name = (await a.get_attribute("aria-label") or "").strip()
                href = await a.get_attribute("href") or ""
                m = _COORD.search(href)
                lat, lng = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
                if name:
                    out.append({"name": name, "address": "", "lat": lat, "lng": lng,
                                "types": "", "place_id": "", "source": "scrape", "query": query})
            await b.close()
    except Exception:
        return out
    return out


async def refresh(query: str, max_results: int = 20) -> int:
    if not await is_online():
        return 0
    places = await _api_text(query)
    if not places:
        places = await _scrape(query, max_results)
    return upsert(places) if places else 0


async def geocode(address: str) -> dict | None:
    if not _key() or not await is_online():
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(_GEOCODE, params={"address": address, "key": _key()})
        res = r.json().get("results", [])
        if not res:
            return None
        loc = res[0]["geometry"]["location"]
        return {"formatted_address": res[0].get("formatted_address", ""),
                "lat": loc["lat"], "lng": loc["lng"]}
    except Exception:
        return None


# ---- C++ geo engine --------------------------------------------------------
async def near(lat: float, lng: float, radius_km: float = 5.0) -> list[dict]:
    if not GEO_BIN.exists() or not PLACES_TSV.exists():
        return []
    proc = await asyncio.create_subprocess_exec(
        str(GEO_BIN), str(PLACES_TSV), "near", str(lat), str(lng), str(radius_km),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    rows = []
    for line in out.decode().splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append({"id": parts[0], "distance_km": float(parts[1]),
                         "name": parts[2], "address": parts[3]})
    return rows[:25]
