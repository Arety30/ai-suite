"""Core system preset — the base behavior layer prepended to every model call.

Loaded from suite/prompts/core_preset.md (override path via [prompts].core_preset
in config.toml). Keeping it in one place means all local models — chat, agents,
RAG — share the same execution personality, and you tune behavior by editing one
file instead of chasing prompt strings across the codebase.
"""
from __future__ import annotations

from pathlib import Path

from suite.config import settings

_DEFAULT = Path(__file__).parent.parent / "prompts" / "core_preset.md"
PRESET_PATH = Path(
    settings.raw.get("prompts", {}).get("core_preset", str(_DEFAULT))
).expanduser()


def core_preset() -> str:
    return PRESET_PATH.read_text(errors="replace") if PRESET_PATH.exists() else ""


def framed(specific: str) -> str:
    """Prepend the core preset to a task-specific system prompt."""
    preset = core_preset()
    return f"{preset}\n\n---\n\n{specific}" if preset else specific
