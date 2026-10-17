"""Provider contracts + a registry that resolves capabilities to a fallback chain.

This one abstraction removes the largest source of duplication in the archives:
the LLM/STT/TTS call logic that was copied into five `brain.py` / three `stt.py`
files. The core asks for a *capability* ("llm"), never a vendor.

Fully local: every provider is offline (Ollama / Whisper / Piper). The chain is
tried in order so a smaller local model can back up a larger one, but nothing in
it ever reaches the network or needs an API key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol, runtime_checkable

from suite.config import settings


@dataclass
class Reply:
    text: str
    model: str
    tool_calls: list[dict] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def chat(self, messages: list[dict], *, model: str | None = None,
                   tools: list[dict] | None = None) -> Reply: ...

    async def stream(self, messages: list[dict], *,
                     model: str | None = None) -> AsyncIterator[str]: ...


@runtime_checkable
class STTProvider(Protocol):
    name: str

    async def transcribe(self, audio_path: str, *, language: str = "en") -> str: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes: ...


class ProviderError(RuntimeError):
    """Raised by a provider to signal 'I can't serve this — try the next one'."""


class Registry:
    """Holds provider *factories* keyed by (capability, provider-name) and builds
    the resolved fallback chain declared in config.toml [providers.<cap>].chain.
    """

    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], type] = {}

    def register(self, capability: str, name: str):
        def deco(cls):
            self._factories[(capability, name)] = cls
            cls.name = name
            return cls
        return deco

    def build_chain(self, capability: str) -> list:
        spec = settings.providers.get(capability)
        if not spec:
            raise ProviderError(f"No provider chain configured for '{capability}'")
        built = []
        for entry in spec.chain:
            key = (capability, entry["provider"])
            factory = self._factories.get(key)
            if factory is None:
                raise ProviderError(
                    f"Provider '{entry['provider']}' for '{capability}' not registered"
                )
            built.append(factory(**entry.get("options", {})))
        return built

    async def call(self, capability: str, method: str, *args, **kwargs):
        """Try each provider in the chain until one succeeds."""
        last: Exception | None = None
        for provider in self.build_chain(capability):
            try:
                return await getattr(provider, method)(*args, **kwargs)
            except ProviderError as exc:
                last = exc
                continue
        raise ProviderError(f"All '{capability}' providers failed: {last}")


registry = Registry()
