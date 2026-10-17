"""Council routes — route a query to the best local model."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from suite.core import council

router = APIRouter(prefix="/v1/council", tags=["council"])


@router.get("/routes")
async def routes():
    return {"classifier": council.CLASSIFIER, "routes": council.ROUTES}


class AskIn(BaseModel):
    query: str


@router.post("/ask")
async def ask(body: AskIn):
    return await council.ask(body.query)
