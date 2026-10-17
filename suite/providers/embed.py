"""Embedding providers — needed by the documents/RAG service. Ollama local first."""
from __future__ import annotations

import httpx

from suite.providers.base import ProviderError, registry

OLLAMA_URL = "http://localhost:11434"


@registry.register("embed", "ollama")
class OllamaEmbedProvider:
    def __init__(self, model: str = "nomic-embed-text"):
        self.model = model

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        model = model or self.model
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                r = await client.post(
                    f"{OLLAMA_URL}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"ollama embed failed: {exc}") from exc
        vec = r.json().get("embedding")
        if not vec:
            raise ProviderError("ollama returned no embedding")
        return vec
