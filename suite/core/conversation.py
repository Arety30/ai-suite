"""The conversation service: the `ai_router` + ACTION protocol from AbrarAssistant,
made interface-agnostic and de-duplicated. Discord, phone, web and desktop all
call `respond()` — none of them re-implement routing.
"""
from __future__ import annotations

import re

from suite.core import memory, preset
from suite.providers.base import registry

SYSTEM_PROMPT = (
    "You are Abrar Assistant, a helpful local-first AI. Reply normally, or when an "
    "action is needed emit a single line: 'ACTION: <TYPE> <details>'. "
    "Valid types: SEARCH, SPEAK, WRITE_FILE, READ_FILE, SHEET, SLIDES, SHELL, ANALYZE."
)

ACTION_RE = re.compile(r"^ACTION:\s*(?P<type>[A-Z_]+)\s*(?P<details>.*)$", re.MULTILINE)


async def respond(conv_id: int, user_text: str) -> dict:
    """Route one user turn. Returns {'text', 'action'} where action may be None.

    Action dispatch (SEARCH -> search provider, SHELL -> sandbox, etc.) is handled
    by the tools service; here we only classify and record. Kept deliberately thin.
    """
    history = memory.recent_history(conv_id)
    messages = [{"role": "system", "content": preset.framed(SYSTEM_PROMPT)}, *history,
                {"role": "user", "content": user_text}]
    reply = await registry.call("llm", "chat", messages)

    memory.add_message(conv_id, "user", user_text)

    m = ACTION_RE.search(reply.text)
    action = None
    if m:
        action = {"type": m.group("type"), "details": m.group("details").strip()}
    memory.add_message(conv_id, "assistant", reply.text,
                       action=action["type"] if action else None)
    return {"text": reply.text, "action": action, "model": reply.model}
