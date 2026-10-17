"""Vault routes — the Obsidian x NotebookLM surface: unified ask, unified graph,
and semantic link suggestions across notes AND sources.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from suite.core import vault

router = APIRouter(prefix="/v1/vault", tags=["vault"])


class AskIn(BaseModel):
    user_id: int = 1
    question: str
    kinds: list[str] | None = None   # e.g. ["note"] or ["doc"]; default = both


@router.post("/ask")
async def ask(body: AskIn):
    """RAG grounded in the user's notes AND sources together, with typed citations."""
    return await vault.ask(body.user_id, body.question, kinds=body.kinds)


@router.get("/graph")
async def graph(user_id: int = 1):
    """Notes + sources as nodes; explicit [[wiki-links]] + semantic edges."""
    return vault.graph(user_id)


@router.get("/suggest")
async def suggest(note_id: int, user_id: int = 1):
    """Related notes/sources for a note, by meaning — proposed as new links."""
    return {"suggestions": vault.suggest_links(user_id, note_id)}
