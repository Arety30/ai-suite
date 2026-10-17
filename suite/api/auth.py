"""Auth routes + a reusable dependency for protecting other endpoints.

`current_account` is opt-in: when [auth].required is false (default) it lets
requests through anonymously so local single-user mode is unchanged; when true it
demands a valid Bearer token. Add `Depends(current_account)` to any route you want
gated once you turn auth on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from suite.config import settings
from suite.core import auth, memory

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _auth_required() -> bool:
    return bool(settings.raw.get("auth", {}).get("required", False))


def current_account(authorization: str = Header(default="")) -> dict | None:
    """Resolve the caller from a Bearer token. Returns the token payload, or None
    when auth isn't required and no token was sent."""
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if not token:
        if _auth_required():
            raise HTTPException(401, "authentication required")
        return None
    payload = auth.verify_token(token)
    if not payload:
        if _auth_required():
            raise HTTPException(401, "invalid or expired token")
        return None
    return payload


class RegisterIn(BaseModel):
    name: str
    password: str
    org_id: str | None = None


@router.post("/register")
async def register(body: RegisterIn):
    return auth.register(body.name, body.password, body.org_id)


class LoginIn(BaseModel):
    account_id: str
    password: str


@router.post("/login")
async def login(body: LoginIn):
    result = auth.login(body.account_id, body.password)
    if result is None:
        raise HTTPException(401, "invalid account id or password")
    return result


@router.get("/me")
async def me(account: dict = Depends(current_account)):
    if account is None:
        raise HTTPException(401, "not authenticated")
    with memory.connect() as db:
        r = db.execute("SELECT id, name, org_id, created FROM account WHERE id=?",
                       (account["sub"],)).fetchone()
    if not r:
        raise HTTPException(404, "account not found")
    return dict(r)
