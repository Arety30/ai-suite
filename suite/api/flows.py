"""Flows — automation surface for a local n8n (or any HTTP caller).

These endpoints run *synchronously* (unlike /v1/tasks which queues): an n8n HTTP
Request node calls one and waits for the result in the same request, so a flow
can fire an agent or a vault query and use the answer downstream. Fully local —
n8n runs on the same machine; nothing leaves it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from suite.api.auth import current_account
from suite.core import agents, vault

router = APIRouter(prefix="/v1/flows", tags=["flows"])


@router.get("/ping")
async def ping():
    """Connectivity check for wiring up an n8n node."""
    return {"ok": True, "service": "abrar-ai-hub", "agents": len(agents.list_agents())}


class RunIn(BaseModel):
    agent: str = "04-deep-thinker"
    prompt: str


@router.post("/run")
async def run(body: RunIn, account: dict = Depends(current_account)):
    """Run one agent to completion and return its answer (blocking)."""
    result = await agents.run_agent(body.agent, body.prompt)
    return {"agent": body.agent, "answer": result["answer"], "steps": result["steps"]}


class AskIn(BaseModel):
    question: str
    user_id: int = 1


@router.post("/ask")
async def ask(body: AskIn):
    """RAG over the vault — grounded answer with citations, for a flow step."""
    return await vault.ask(body.user_id, body.question)
