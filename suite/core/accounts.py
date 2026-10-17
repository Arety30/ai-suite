"""Local accounts, sessions, device keys and guest mode — all in SQLite.

- Passwords hashed with PBKDF2 (stdlib, no deps).
- Each user gets a random **account key** they can store on their laptop / cloud to
  log in on a NEW device without the password (device linking / recovery).
- **Guest mode**: an ephemeral account with its own data namespace.
- Every user has a data namespace (user id) + a `sync_enabled` flag; because all
  devices reach the one gateway over the tailnet, their data is shared across
  devices automatically when sync is on.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime, timedelta

from suite.config import settings

DB = settings.data_dir / "accounts.db"
_ITER = 200_000
SESSION_DAYS = 30
COOKIE = "session"

_conn = sqlite3.connect(str(DB), check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("""CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT,
    role TEXT DEFAULT 'user', account_key TEXT, sync_enabled INTEGER DEFAULT 1,
    is_guest INTEGER DEFAULT 0, created_at TEXT)""")
_conn.execute("""CREATE TABLE IF NOT EXISTS sessions(
    token TEXT PRIMARY KEY, user_id INTEGER, expires TEXT, created_at TEXT)""")
_conn.commit()


# --- passwords --------------------------------------------------------------
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _a, it, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), want)
    except Exception:
        return False


# --- users ------------------------------------------------------------------
def user_count() -> int:
    return _conn.execute("SELECT COUNT(*) c FROM users WHERE is_guest=0").fetchone()["c"]


def get_user(username: str):
    return _conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def user_by_key(key: str):
    if not key:
        return None
    return _conn.execute("SELECT * FROM users WHERE account_key=?", (key,)).fetchone()


def create_user(username: str, password: str) -> dict:
    role = "admin" if user_count() == 0 else "user"
    key = secrets.token_urlsafe(24)
    _conn.execute(
        "INSERT INTO users(username,password_hash,role,account_key,created_at) VALUES(?,?,?,?,?)",
        (username.strip(), hash_password(password), role, key,
         datetime.now().isoformat(timespec="seconds")))
    _conn.commit()
    u = get_user(username)
    return {"id": u["id"], "username": u["username"], "role": u["role"], "account_key": key}


def create_guest() -> dict:
    name = "guest_" + secrets.token_hex(4)
    key = secrets.token_urlsafe(24)
    _conn.execute(
        "INSERT INTO users(username,password_hash,role,account_key,is_guest,created_at) "
        "VALUES(?,?,?,?,1,?)",
        (name, "", "guest", key, datetime.now().isoformat(timespec="seconds")))
    _conn.commit()
    u = get_user(name)
    return {"id": u["id"], "username": name, "role": "guest", "account_key": key}


def set_sync(user_id: int, enabled: bool) -> None:
    _conn.execute("UPDATE users SET sync_enabled=? WHERE id=?", (1 if enabled else 0, user_id))
    _conn.commit()


# --- sessions ---------------------------------------------------------------
def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat()
    _conn.execute("INSERT INTO sessions(token,user_id,expires,created_at) VALUES(?,?,?,?)",
                  (token, user_id, expires, datetime.now().isoformat(timespec="seconds")))
    _conn.commit()
    return token


def user_for_token(token: str | None):
    if not token:
        return None
    row = _conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    if row["expires"] and row["expires"] < datetime.now().isoformat():
        _conn.execute("DELETE FROM sessions WHERE token=?", (token,)); _conn.commit()
        return None
    return _conn.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()


def delete_session(token: str | None) -> None:
    if token:
        _conn.execute("DELETE FROM sessions WHERE token=?", (token,)); _conn.commit()
