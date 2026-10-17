#!/usr/bin/env python3
"""Desktop (ai-hub) adapter — the thin bridge that makes the ai-hub desktop/web
shell a client of the suite gateway.

Per the suite design, the ai-hub UI should call the ONE gateway instead of its
own backend. This adapter exposes the gateway's capabilities in the shape the
ai-hub frontend expects, so pointing ai-hub at it is a drop-in.

  python adapters/desktop.py health
  python adapters/desktop.py chat "hello"
  python adapters/desktop.py maps  "cafes in Karachi"
  python adapters/desktop.py near  24.81 67.03 5

All logic lives in the suite core; this only talks HTTP. Fully local.
"""
from __future__ import annotations

import sys

import httpx

GATEWAY = "http://127.0.0.1:8100"


def _c() -> httpx.Client:
    return httpx.Client(base_url=GATEWAY, timeout=180)


def health():
    print(_c().get("/health").json())


def chat(text: str):
    print(_c().post("/v1/chat", json={"message": text}).json().get("text", ""))


def maps(query: str):
    r = _c().get("/v1/maps/search", params={"q": query}).json()
    for p in r.get("places", []):
        print(f"  {p['name']}", p.get("address", ""))


def near(lat: str, lng: str, radius: str = "5"):
    r = _c().get("/v1/maps/near", params={"lat": lat, "lng": lng, "radius_km": radius}).json()
    for p in r.get("places", []):
        print(f"  {p['name']} — {p['distance_km']} km")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd, args = sys.argv[1], sys.argv[2:]
    {"health": lambda: health(),
     "chat": lambda: chat(" ".join(args)),
     "maps": lambda: maps(" ".join(args)),
     "near": lambda: near(*args)}.get(cmd, lambda: print(f"unknown: {cmd}"))()


if __name__ == "__main__":
    main()
