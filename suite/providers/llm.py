"""LLM provider — Ollama only. Fully local, no API keys, no cloud.

Consolidates the copies of brain.py from AbrarAssistant, ai_receptionist,
projectonebeta and council.py — including the RAM-OOM fallback that
projectonebeta's logs hit (a model needing more memory than available). That
fallback now lives here, once. There is deliberately no cloud provider: the
suite runs entirely against a local Ollama.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from suite.providers.base import ProviderError, Reply, registry

OLLAMA_URL = "http://localhost:11434"


@registry.register("llm", "ollama")
class OllamaProvider:
    def __init__(self, model: str = "llama3.2:1b", fallback_model: str | None = None):
        self.model = model
        self.fallback_model = fallback_model

    async def chat(self, messages, *, model=None, tools=None, format=None) -> Reply:
        model = model or self.model
        payload = {"model": model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        if format:  # e.g. "json" forces valid-JSON output for structured tasks
            payload["format"] = format
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Model won't fit in RAM -> drop to the smaller fallback model.
                if (self.fallback_model and model != self.fallback_model
                        and "memory" in exc.response.text.lower()):
                    return await self.chat(messages, model=self.fallback_model, tools=tools)
                raise ProviderError(f"ollama chat failed: {exc}") from exc
            except httpx.HTTPError as exc:
                raise ProviderError(f"ollama unreachable at {OLLAMA_URL}: {exc}") from exc
        data = r.json()
        msg = data.get("message", {})
        return Reply(text=msg.get("content", ""), model=model,
                     tool_calls=msg.get("tool_calls"))

    async def stream(self, messages, *, model=None) -> AsyncIterator[str]:
        model = model or self.model
        payload = {"model": model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as r:
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    yield chunk.get("message", {}).get("content", "")
