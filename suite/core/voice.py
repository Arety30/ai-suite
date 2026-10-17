"""The one voice loop: STT -> conversation -> TTS. Reused by the phone adapter
(Vapi/Asterisk), the web console, and Discord /speak — instead of each project
carrying its own copy (projectonebeta's server.py, betaone.py, ai_receptionist).
"""
from __future__ import annotations

from suite.core import conversation
from suite.providers.base import registry


async def transcribe(audio_path: str, *, language: str = "en") -> str:
    return await registry.call("stt", "transcribe", audio_path, language=language)


async def speak(text: str, *, voice: str | None = None) -> bytes:
    return await registry.call("tts", "synthesize", text, voice=voice)


async def converse(conv_id: int, audio_path: str, *, language: str = "en") -> dict:
    """Full loop: audio in -> transcript -> reply -> audio out."""
    text = await transcribe(audio_path, language=language)
    result = await conversation.respond(conv_id, text)
    audio = await speak(result["text"])
    return {"transcript": text, "reply": result["text"],
            "action": result["action"], "audio": audio}
