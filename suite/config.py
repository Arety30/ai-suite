"""Single source of configuration for the whole suite.

The suite is fully local and offline: there are no API keys and no cloud
providers, so there is no secrets store. Everything runs against a local Ollama
plus local Whisper/Piper models cached under data/. This file just resolves the
provider chains and storage paths from config.toml.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("SUITE_CONFIG", ROOT / "config.toml"))


@dataclass
class ProviderChain:
    """An ordered fallback chain for one capability (llm, stt, tts, ...)."""

    capability: str
    chain: list[dict] = field(default_factory=list)


@dataclass
class Settings:
    data_dir: Path = ROOT / "data"
    db_url: str = f"sqlite:///{ROOT / 'data' / 'suite.db'}"
    host: str = "127.0.0.1"
    port: int = 8100
    jwt_secret_name: str = "jwt_secret"
    providers: dict[str, ProviderChain] = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def _load_toml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as fh:
            return tomllib.load(fh)
    return {}


def load_settings() -> Settings:
    raw = _load_toml()
    s = Settings(raw=raw)
    srv = raw.get("server", {})
    s.host = srv.get("host", s.host)
    s.port = int(srv.get("port", s.port))
    s.db_url = raw.get("storage", {}).get("db_url", s.db_url)
    for cap, spec in raw.get("providers", {}).items():
        s.providers[cap] = ProviderChain(capability=cap, chain=spec.get("chain", []))
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


settings = load_settings()
