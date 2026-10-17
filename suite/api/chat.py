"""Conversation routes, including an OpenAI-compatible endpoint so Vapi and any
off-the-shelf client can talk to the local core unchanged (the endpoint
projectonebeta already needed).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from suite.core import conversation, memory, preset
from suite.providers.base import ProviderError, registry

router = APIRouter(prefix="/v1", tags=["chat"])


class ChatIn(BaseModel):
    conversation_id: int = 1
    message: str


@router.post("/chat")
async def chat(body: ChatIn):
    return await conversation.respond(body.conversation_id, body.message)


@router.websocket("/stream")
async def stream(ws: WebSocket):
    """Token-streaming chat over WebSocket — the real-time foundation P7 telephony
    needs (audio/text must flow as it's produced, not in one blocking response).
    Client sends {"conversation_id": int, "message": str}; server streams
    {"type":"token","text":...} frames then {"type":"done","text": full}."""
    await ws.accept()
    try:
        req = await ws.receive_json()
    except Exception:
        await ws.close(code=1003)
        return
    conv_id = int(req.get("conversation_id", 1))
    msg = str(req.get("message", ""))
    history = memory.recent_history(conv_id)
    messages = [{"role": "system", "content": preset.framed(conversation.SYSTEM_PROMPT)},
                *history, {"role": "user", "content": msg}]
    memory.add_message(conv_id, "user", msg)
    parts: list[str] = []
    try:
        provider = registry.build_chain("llm")[0]  # streaming uses the primary provider
        async for token in provider.stream(messages):
            parts.append(token)
            await ws.send_json({"type": "token", "text": token})
        full = "".join(parts)
        memory.add_message(conv_id, "assistant", full)
        await ws.send_json({"type": "done", "text": full})
    except (ProviderError, Exception) as exc:  # noqa: BLE001 - report, don't 500
        await ws.send_json({"type": "error", "detail": str(exc)})
    finally:
        await ws.close()


# ---- OpenAI-compatible surface (for Vapi / generic clients) ----------------

class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str | None = None
    messages: list[OAIMessage]
    stream: bool = False


@router.post("/chat/completions")
async def chat_completions(body: OAIRequest):
    reply = await registry.call(
        "llm", "chat", [m.model_dump() for m in body.messages], model=body.model
    )
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": reply.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply.text},
            "finish_reason": "stop",
        }],
    }
