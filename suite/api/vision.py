"""Vision routes — describe or answer questions about an uploaded image, locally."""
from __future__ import annotations

import base64

from fastapi import APIRouter, UploadFile

from suite.providers.base import registry

router = APIRouter(prefix="/v1/vision", tags=["vision"])


@router.post("/describe")
async def describe(file: UploadFile, prompt: str = "Describe this image in detail."):
    """Analyze an image with the local vision model. `prompt` can be a question."""
    b64 = base64.b64encode(await file.read()).decode()
    text = await registry.call("vision", "describe", b64, prompt=prompt)
    return {"description": text}
