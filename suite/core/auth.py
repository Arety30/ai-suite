"""Authentication — salted password hashing + a minimal HS256 JWT, all stdlib.

No external deps (keeps the suite lean and offline). Accounts (from orgs.py) get a
password hash; login returns a signed token. Auth is OPT-IN: it's only enforced on
routes that depend on it when [auth].required = true, so the default local
single-user experience is unchanged.

Replaces StudySync's unsalted SHA-256 + never-expiring tokens.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from suite.config import settings
from suite.core import identity, memory

PBKDF_ROUNDS = 100_000
TOKEN_TTL = 7 * 24 * 3600  # 7 days
_SECRET_FILE = settings.data_dir / "auth_secret.key"


# ---- signing secret (persisted, generated once) -----------------------------

def secret() -> str:
    configured = settings.raw.get("auth", {}).get("secret")
    if configured:
        return configured
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()
    gen = secrets.token_hex(32)
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_text(gen)
    return gen


# ---- password hashing -------------------------------------------------------

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), PBKDF_ROUNDS)
    return f"{salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), PBKDF_ROUNDS)
    return hmac.compare_digest(dk.hex(), h)


# ---- JWT (HS256) ------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(account_id: str, **claims) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    body = _b64(json.dumps({"sub": account_id, "iat": now,
                            "exp": now + TOKEN_TTL, **claims}).encode())
    seg = f"{header}.{body}"
    sig = _b64(hmac.new(secret().encode(), seg.encode(), hashlib.sha256).digest())
    return f"{seg}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        header, body, sig = token.split(".")
        seg = f"{header}.{body}"
        expected = _b64(hmac.new(secret().encode(), seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 - any malformed token is simply invalid
        return None


# ---- account register / login ----------------------------------------------

def register(name: str, password: str, org_id: str | None = None) -> dict:
    aid = identity.generate_id()
    with memory.connect() as db:
        db.execute("INSERT INTO account (id, name, org_id, pw_hash) VALUES (?,?,?,?)",
                   (aid, name, org_id, hash_password(password)))
    return {"account_id": aid, "name": name, "org_id": org_id,
            "token": create_token(aid, name=name)}


def login(account_id: str, password: str) -> dict | None:
    with memory.connect() as db:
        r = db.execute("SELECT id, name, org_id, pw_hash FROM account WHERE id=?",
                       (account_id,)).fetchone()
    if not r or not verify_password(password, r["pw_hash"]):
        return None
    return {"account_id": r["id"], "name": r["name"], "org_id": r["org_id"],
            "token": create_token(r["id"], name=r["name"])}
