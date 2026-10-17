"""Council — a local task-based model router.

Reimagines projectonebeta/council.py (triage locally, then call cloud Gemini) as
a fully-local router: classify the request, then answer with the best-suited local
Ollama model. Classification is a fast, deterministic keyword heuristic (a 1B LLM
classifier is unreliable); an optional LLM classifier can back it up for ambiguous
requests via [council].use_llm_classifier = true.
"""
from __future__ import annotations

import json
import re

from suite.config import settings
from suite.core.documents import _first_json_block
from suite.providers.base import registry

_cfg = settings.raw.get("council", {})
ROUTES: dict = _cfg.get("routes", {
    "code": "qwen2.5-coder:1.5b",     # programming, scripts, debugging
    "reasoning": "deepseek-r1:1.5b",  # math, logic, multi-step analysis
    "general": "llama3.2:1b",         # everything else
})
CLASSIFIER: str = _cfg.get("classifier", "llama3.2:1b")
USE_LLM = bool(_cfg.get("use_llm_classifier", False))

_CODE_KW = re.compile(
    r"\b(code|coding|function|python|javascript|typescript|java|c\+\+|rust|"
    r"script|program|programming|debug|bug|compile|regex|sql|api|algorithm|"
    r"stack ?trace|traceback|syntax|refactor)\b|(?:^|\s)(def |class |import )", re.I)
_REASON_KW = re.compile(
    r"\b(calculate|compute|solve|prove|proof|logic|math|maths|equation|derive|"
    r"theorem|how many|step[- ]by[- ]step|reason through|work out|probability)\b", re.I)


async def _llm_classify(query: str) -> str:
    prompt = [
        {"role": "system", "content":
            'Classify the request into exactly one of: "code", "reasoning", or '
            '"general". Respond ONLY as JSON: {"category":"..."}.'},
        {"role": "user", "content": query},
    ]
    reply = await registry.call("llm", "chat", prompt, model=CLASSIFIER, format="json")
    try:
        cat = json.loads(_first_json_block(reply.text) or "{}").get("category", "general")
    except json.JSONDecodeError:
        cat = "general"
    return cat if cat in ROUTES else "general"


async def classify(query: str) -> str:
    if _CODE_KW.search(query):
        return "code"
    if _REASON_KW.search(query):
        return "reasoning"
    if USE_LLM:
        return await _llm_classify(query)
    return "general"


async def ask(query: str) -> dict:
    """Route the query to the best local model and answer it."""
    cat = await classify(query)
    model = ROUTES[cat]
    reply = await registry.call("llm", "chat",
                                [{"role": "user", "content": query}], model=model)
    return {"category": cat, "model": model, "answer": reply.text}
