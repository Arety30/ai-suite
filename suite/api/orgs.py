"""Organization & account routes — schools/companies and their members."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from suite.core import orgs

router = APIRouter(prefix="/v1", tags=["orgs"])


class OrgIn(BaseModel):
    name: str
    type: str = "company"   # school | company


@router.post("/orgs")
async def create_org(body: OrgIn):
    return orgs.create_org(body.name, body.type)


@router.get("/orgs")
async def list_orgs():
    return orgs.list_orgs()


@router.get("/orgs/{org_id}")
async def get_org(org_id: str):
    o = orgs.get_org(org_id)
    if o is None:
        raise HTTPException(404, "organization not found")
    return {**o, "members": orgs.org_members(org_id)}


class AccountIn(BaseModel):
    name: str
    org_id: str | None = None   # omit for a normal (unaffiliated) user


@router.post("/accounts")
async def create_account(body: AccountIn):
    if body.org_id and orgs.get_org(body.org_id) is None:
        raise HTTPException(404, "organization not found")
    return orgs.create_account(body.name, body.org_id)


@router.get("/accounts/{account_id}")
async def get_account(account_id: str):
    a = orgs.get_account(account_id)
    if a is None:
        raise HTTPException(404, "account not found")
    return a
