"""Studio API — serves the polished 'AI Suite Studio' frontend against LOCAL
Ollama instead of Gemini. Implements the exact /api/* contract the studio's
server.ts used, so the built frontend works unchanged — but 100% offline.
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["studio"])
OLLAMA = "http://localhost:11434"

# Map the Gemini model names the UI sends → local Ollama models.
_MODEL_MAP = {
    "gemini-2.5-flash": "llama3.2:1b",
    "gemini-2.0-flash": "gemma3:1b",
    "gemini-2.5-pro": "qwen2.5-coder:1.5b",
    "gemini-1.5-pro": "deepseek-r1:1.5b",
}
_VISION = "granite3.2-vision:2b"


def _local(model: str | None) -> str:
    return _MODEL_MAP.get(model or "", "llama3.2:1b")


def _tok(s: str) -> int:
    return max(1, len(s) // 4)


async def _ollama(messages: list[dict], model: str, options: dict | None = None) -> str:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{OLLAMA}/api/chat",
                         json={"model": model, "messages": messages, "stream": False,
                               "options": options or {}})
        r.raise_for_status()
    return r.json().get("message", {}).get("content", "")


@router.get("/api/status")
async def status():
    online = True
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            await c.get(f"{OLLAMA}/api/tags")
    except Exception:
        online = False
    return {"status": "online" if online else "offline",
            "apiKeyConfigured": True,        # local — no key needed
            "environment": "local", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ")}


class ChatIn(BaseModel):
    prompt: str | None = None
    messages: list[dict] | None = None
    model: str = "gemini-2.5-flash"
    systemInstruction: str | None = None
    temperature: float = 0.7
    topP: float = 0.95
    topK: int = 40
    maxOutputTokens: int = 2048


@router.post("/api/chat")
async def chat(body: ChatIn):
    start = time.time()
    msgs: list[dict] = []
    if body.systemInstruction:
        msgs.append({"role": "system", "content": body.systemInstruction})
    if body.messages:
        for m in body.messages:
            role = "assistant" if m.get("role") == "assistant" else \
                   ("system" if m.get("role") == "system" else "user")
            msgs.append({"role": role, "content": m.get("content", "")})
    elif body.prompt:
        msgs.append({"role": "user", "content": body.prompt})

    model = _local(body.model)
    opts = {"temperature": body.temperature, "top_p": body.topP,
            "top_k": body.topK, "num_predict": body.maxOutputTokens}
    try:
        text = await _ollama(msgs, model, opts)
    except Exception as e:
        return JSONResponse({"error": str(e), "latencyMs": int((time.time() - start) * 1000)},
                            status_code=503)
    inp = _tok(" ".join(m["content"] for m in msgs))
    out = _tok(text)
    return {"content": text, "model": model,
            "latencyMs": int((time.time() - start) * 1000),
            "tokens": {"input": inp, "output": out, "total": inp + out}}


class CompareIn(BaseModel):
    prompt: str
    modelA: str = "gemini-2.5-flash"
    modelB: str = "gemini-2.5-pro"
    systemInstruction: str | None = None


@router.post("/api/compare")
async def compare(body: CompareIn):
    async def run(model_name: str):
        start = time.time()
        msgs = []
        if body.systemInstruction:
            msgs.append({"role": "system", "content": body.systemInstruction})
        msgs.append({"role": "user", "content": body.prompt})
        try:
            text = await _ollama(msgs, _local(model_name), {"temperature": 0.7})
            return {"content": text, "latencyMs": int((time.time() - start) * 1000),
                    "tokens": {"input": _tok(body.prompt), "output": _tok(text)}}
        except Exception as e:
            return {"content": "", "latencyMs": int((time.time() - start) * 1000),
                    "tokens": {"input": 0, "output": 0}, "error": str(e)}
    a = await run(body.modelA)
    b = await run(body.modelB)
    return {"responseA": a, "responseB": b, "modelA": body.modelA, "modelB": body.modelB}


class ImageIn(BaseModel):
    prompt: str = "Analyze this image and extract key insights or code"
    imageBase64: str
    mimeType: str = "image/jpeg"


@router.post("/api/analyze-image")
async def analyze_image(body: ImageIn):
    start = time.time()
    b64 = body.imageBase64.split(",")[-1]  # strip data: header if present
    try:
        text = await _ollama([{"role": "user", "content": body.prompt, "images": [b64]}], _VISION)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    return {"analysisText": text, "latencyMs": int((time.time() - start) * 1000), "model": _VISION}
