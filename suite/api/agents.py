"""Agent routes: list the swarm, queue a task, poll it."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from suite.api.auth import current_account
from suite.core import agents

router = APIRouter(prefix="/v1", tags=["agents"])


@router.get("/agents")
async def list_agents():
    return agents.list_agents()


class TaskIn(BaseModel):
    agent: str
    prompt: str


@router.post("/tasks")
async def create_task(body: TaskIn, account: dict = Depends(current_account)):
    task_id = agents.create_task(body.agent, body.prompt)
    return {"task_id": task_id, "status": "queued"}


@router.get("/tasks/{task_id}")
async def get_task(task_id: int):
    task = agents.get_task(task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return task
