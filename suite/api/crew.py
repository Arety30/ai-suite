"""Crew routes — assemble AI coworkers, give them a goal, watch them collaborate."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from suite.api.auth import current_account
from suite.core import crew

router = APIRouter(prefix="/v1/crew", tags=["crew"])


@router.get("/coworkers")
async def coworkers():
    """The roster of AI coworkers a crew can draw from."""
    return crew.roster()


class RunIn(BaseModel):
    goal: str


@router.post("/run")
async def run(body: RunIn, account: dict = Depends(current_account)):
    """Kick off a crew on a goal. Returns a run id to poll."""
    return {"run_id": crew.create_run(body.goal), "status": "queued"}


@router.get("/runs")
async def runs():
    return crew.list_runs()


@router.get("/runs/{run_id}")
async def get_run(run_id: int):
    r = crew.get_run(run_id)
    if r is None:
        raise HTTPException(404, "crew run not found")
    return r
