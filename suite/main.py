"""The gateway: one FastAPI app that mounts a router per capability.

Run:  uvicorn suite.main:app --reload --port 8100
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import suite.providers  # noqa: F401  -- registers all providers on import
from suite.api import (account, agents, auth, chat, create, crew, council, flows, knowledge,
                       maps, meetings, n8n, orgs, studio, system, vault, vision, voice)
from suite.core import accounts as _acc
from fastapi.responses import RedirectResponse, FileResponse
from suite.config import settings
from suite.core import memory
from suite.providers.base import ProviderError

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory.init_db()
    yield


app = FastAPI(title="Abrar AI Hub — Suite", version="0.1.0", lifespan=lifespan)

# Public paths reachable without a login (login page, auth API, health, static assets).
_PUBLIC_PREFIX = ("/login", "/api/auth", "/health", "/assets", "/favicon",
                  "/manifest", "/vite.svg", "/icon")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if not any(path == p or path.startswith(p) for p in _PUBLIC_PREFIX):
        user = _acc.user_for_token(request.cookies.get(_acc.COOKIE))
        if not user:
            if path.startswith("/api") or path.startswith("/v1"):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
            return RedirectResponse("/login")
    return await call_next(request)


app.include_router(account.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(knowledge.router)
app.include_router(agents.router)
app.include_router(vault.router)
app.include_router(create.router)
app.include_router(flows.router)
app.include_router(system.router)
app.include_router(crew.router)
app.include_router(meetings.router)
app.include_router(orgs.router)
app.include_router(auth.router)
app.include_router(n8n.router)
app.include_router(vision.router)
app.include_router(council.router)
app.include_router(maps.router)
app.include_router(studio.router)   # /api/* for the polished Studio UI (local Ollama)


@app.exception_handler(ProviderError)
async def provider_unavailable(request: Request, exc: ProviderError):
    """Every provider in a chain failed — report it as a clear 503, not a 500."""
    return JSONResponse(status_code=503, content={"error": "provider_unavailable",
                                                  "detail": str(exc)})


@app.get("/health")
async def health():
    return {
        "ok": True,
        "providers": {cap: [e["provider"] for e in chain.chain]
                      for cap, chain in settings.providers.items()},
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    p = WEB_DIR / "login.html"
    return p.read_text() if p.exists() else "<h1>login page missing</h1>"


# Serve the polished 'AI Suite Studio' frontend (built) as the web UI.
# Mounted LAST so /v1/*, /api/* and /health match first; StaticFiles serves the rest.
_STUDIO_DIST = Path(__file__).parent.parent / "studio" / "dist"
if _STUDIO_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_STUDIO_DIST), html=True), name="studio")
