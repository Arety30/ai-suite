"""Auth endpoints: password login, device-key login, guest mode, sync toggle."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from suite.core import accounts as acc

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _session(resp: JSONResponse, token: str, request: Request):
    resp.set_cookie(acc.COOKIE, token, httponly=True, samesite="lax",
                    secure=_https(request), max_age=acc.SESSION_DAYS * 86400)


class Creds(BaseModel):
    username: str = ""
    password: str = ""


class KeyIn(BaseModel):
    key: str


@router.get("/status")
async def status():
    return {"registered": acc.user_count() > 0}


@router.post("/register")
async def register(body: Creds, request: Request):
    if len(body.username) < 3 or len(body.password) < 6:
        return JSONResponse({"detail": "username ≥3 and password ≥6 chars"}, status_code=400)
    if acc.get_user(body.username):
        return JSONResponse({"detail": "username taken"}, status_code=400)
    u = acc.create_user(body.username, body.password)
    resp = JSONResponse({"ok": True, "username": u["username"], "role": u["role"],
                         "account_key": u["account_key"]})   # show ONCE — save it
    _session(resp, acc.create_session(u["id"]), request)
    return resp


@router.post("/login")
async def login(body: Creds, request: Request):
    u = acc.get_user(body.username)
    if not u or not acc.verify_password(body.password, u["password_hash"]):
        return JSONResponse({"detail": "invalid username or password"}, status_code=401)
    resp = JSONResponse({"ok": True, "username": u["username"], "role": u["role"]})
    _session(resp, acc.create_session(u["id"]), request)
    return resp


@router.post("/login-key")
async def login_key(body: KeyIn, request: Request):
    """Log in on a NEW device using the account key (no password needed)."""
    u = acc.user_by_key(body.key.strip())
    if not u:
        return JSONResponse({"detail": "invalid account key"}, status_code=401)
    resp = JSONResponse({"ok": True, "username": u["username"], "role": u["role"]})
    _session(resp, acc.create_session(u["id"]), request)
    return resp


@router.post("/guest")
async def guest(request: Request):
    """Start a guest session with its own data namespace."""
    u = acc.create_guest()
    resp = JSONResponse({"ok": True, "username": u["username"], "role": "guest",
                         "account_key": u["account_key"]})
    _session(resp, acc.create_session(u["id"]), request)
    return resp


@router.post("/logout")
async def logout(request: Request):
    acc.delete_session(request.cookies.get(acc.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(acc.COOKIE)
    return resp


@router.get("/me")
async def me(request: Request):
    u = acc.user_for_token(request.cookies.get(acc.COOKIE))
    if not u:
        return {}
    return {"username": u["username"], "role": u["role"],
            "is_guest": bool(u["is_guest"]), "sync_enabled": bool(u["sync_enabled"])}


class SyncIn(BaseModel):
    enabled: bool


@router.post("/sync")
async def sync(body: SyncIn, request: Request):
    u = acc.user_for_token(request.cookies.get(acc.COOKIE))
    if not u:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    acc.set_sync(u["id"], body.enabled)
    return {"ok": True, "sync_enabled": body.enabled}
