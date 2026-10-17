"""Voice routes — transcribe, speak, and the full converse loop."""
from __future__ import annotations

import tempfile

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel

from suite.core import voice

router = APIRouter(prefix="/v1/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe(file: UploadFile, language: str = "en"):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    return {"text": await voice.transcribe(path, language=language)}


class SpeakIn(BaseModel):
    text: str
    voice: str | None = None


@router.post("/speak")
async def speak(body: SpeakIn):
    audio = await voice.speak(body.text, voice=body.voice)
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/converse")
async def converse(file: UploadFile, conversation_id: int = 1, language: str = "en"):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    result = await voice.converse(conversation_id, path, language=language)
    result.pop("audio", None)  # audio fetched separately via /speak
    return result
