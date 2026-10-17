"""Vision provider — local image understanding via Ollama (granite3.2-vision).

Ports the image-analysis capability from AbrarAssistant/image_service.py and
discord_bot/vision.py (which sent base64 images to a local LLaVA). Fully local.

Note: a 2B vision model needs ~3.5-4 GB free RAM (no GPU here). On low-memory
machines Ollama gets OOM-killed loading it; the provider surfaces that clearly.
"""
from __future__ import annotations

import httpx

from suite.providers.base import ProviderError, registry

OLLAMA_URL = "http://localhost:11434"


@registry.register("vision", "ollama")
class OllamaVisionProvider:
    def __init__(self, model: str = "granite3.2-vision:2b"):
        self.model = model

    async def describe(self, image_b64: str, *,
                       prompt: str = "Describe this image in detail.") -> str:
        payload = {"model": self.model, "prompt": prompt,
                   "images": [image_b64], "stream": False}
        async with httpx.AsyncClient(timeout=240) as client:
            try:
                r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
                r.raise_for_status()
            except (httpx.RemoteProtocolError, httpx.ReadError):
                # Ollama dropped the connection — almost always OOM on model load.
                raise ProviderError(
                    f"vision model '{self.model}' could not load (Ollama disconnected — "
                    "usually out of memory; a 2B vision model needs ~3.5-4 GB free RAM "
                    "and no GPU is available). Free memory or use a smaller model.")
            except httpx.HTTPError as exc:
                raise ProviderError(f"vision model failed: {exc}") from exc
        return r.json().get("response", "").strip()
