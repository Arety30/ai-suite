"""STT and TTS providers — fully local, no API keys, no network at runtime.

  STT  = faster-whisper (CTranslate2, CPU, int8). No torch, no cloud.
  TTS  = Piper (ONNX voices). Runs entirely offline.

Replaces the three copied STT modules (root / STT / STT_backup in projectonebeta)
and every ElevenLabs/gTTS call site — none of which were offline. Models are
cached under data/ after first download, then the suite needs no network.
"""
from __future__ import annotations

import io
import wave
from pathlib import Path

from suite.config import settings
from suite.providers.base import ProviderError, registry

# ---- STT -------------------------------------------------------------------


@registry.register("stt", "whisper")
class WhisperProvider:
    """Local faster-whisper. `model_size` in {tiny, base, small, ...}; tiny is
    fast and CPU-friendly. Weights cache under data/whisper on first use."""

    def __init__(self, model_size: str = "tiny", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ProviderError("faster-whisper not installed") from exc
            cache = str(settings.data_dir / "whisper")
            self._model = WhisperModel(
                self.model_size, device="cpu",
                compute_type=self.compute_type, download_root=cache,
            )
        return self._model

    async def transcribe(self, audio_path: str, *, language: str = "en") -> str:
        model = self._load()
        segments, _info = model.transcribe(audio_path, language=language)
        return " ".join(s.text for s in segments).strip()


# ---- TTS -------------------------------------------------------------------


@registry.register("tts", "piper")
class PiperProvider:
    """Local Piper TTS. Point `voice_path` at a downloaded .onnx voice (with its
    .onnx.json alongside). Returns WAV bytes — no cloud, no key."""

    def __init__(self, voice_path: str = "data/voices/en_US-amy-low.onnx"):
        self.voice_path = voice_path
        self._voice = None

    def _load(self):
        if self._voice is None:
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise ProviderError("piper-tts not installed") from exc
            path = Path(self.voice_path)
            if not path.is_absolute():
                path = settings.data_dir.parent / self.voice_path
            if not path.exists():
                raise ProviderError(
                    f"piper voice not found at {path}. Download one, e.g.:\n"
                    "  see README 'Local models' — en_US-amy-low.onnx(.json)"
                )
            self._voice = PiperVoice.load(str(path))
        return self._voice

    async def synthesize(self, text: str, *, voice: str | None = None) -> bytes:
        piper_voice = self._load()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            piper_voice.synthesize_wav(text, wf)
        return buf.getvalue()
