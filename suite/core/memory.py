"""The single memory store — replaces AbrarAssistant's memory.db, OpenManus's
StateManager, StudySync's in-memory dicts, and the browsers' localStorage.

SQLite to start; one migration from Postgres + pgvector when RAG/graph grow.
Only the schema + a thin accessor live here; services talk to this, never to
their own private database.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from suite.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
  id INTEGER PRIMARY KEY, handle TEXT UNIQUE, pw_hash TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversation (
  id INTEGER PRIMARY KEY, user_id INTEGER, surface TEXT, title TEXT,
  updated TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS message (
  id INTEGER PRIMARY KEY, conv_id INTEGER, role TEXT, content TEXT,
  action TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document (
  id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, source TEXT,
  category TEXT, text TEXT
);
CREATE TABLE IF NOT EXISTS chunk (
  id INTEGER PRIMARY KEY, doc_id INTEGER, ordinal INTEGER, text TEXT, embedding BLOB
);
CREATE TABLE IF NOT EXISTS note (
  id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, body TEXT,
  tags TEXT, links TEXT, updated TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meeting (
  id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, start_time TEXT,
  participants TEXT, transcript TEXT,
  type TEXT DEFAULT 'normal', meta TEXT DEFAULT '{}',
  org_id TEXT, join_code TEXT, host_backend TEXT DEFAULT 'local', host_url TEXT
);
CREATE TABLE IF NOT EXISTS task (
  id INTEGER PRIMARY KEY, agent TEXT, prompt TEXT, status TEXT DEFAULT 'queued',
  result TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Identity: organizations (school/company) and accounts, each with an 18-char
-- public id (12 digits + 6 letters). Normal users are just accounts with no org.
CREATE TABLE IF NOT EXISTS organization (
  id TEXT PRIMARY KEY, name TEXT, type TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account (
  id TEXT PRIMARY KEY, name TEXT, org_id TEXT, pw_hash TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Crew: a multi-agent collaboration run (manager plan + per-coworker steps + result).
CREATE TABLE IF NOT EXISTS crew_run (
  id INTEGER PRIMARY KEY, goal TEXT, status TEXT DEFAULT 'queued',
  plan TEXT, steps TEXT, result TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
);
-- Unified vault index: notes AND documents embed into the SAME table, so
-- retrieval and the graph span both (the Obsidian x NotebookLM combination).
CREATE TABLE IF NOT EXISTS vault_chunk (
  id INTEGER PRIMARY KEY, user_id INTEGER, kind TEXT, ref_id INTEGER,
  title TEXT, ordinal INTEGER, text TEXT, embedding TEXT
);
CREATE INDEX IF NOT EXISTS ix_vault_user ON vault_chunk(user_id);
CREATE INDEX IF NOT EXISTS ix_vault_ref  ON vault_chunk(kind, ref_id);
"""

_DB_PATH = Path(settings.db_url.replace("sqlite:///", ""))


def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)
        # migrate pre-existing DBs that lack newer meeting columns
        for col, decl in [("type", "TEXT DEFAULT 'normal'"), ("meta", "TEXT DEFAULT '{}'"),
                          ("org_id", "TEXT"), ("join_code", "TEXT"),
                          ("host_backend", "TEXT DEFAULT 'local'"), ("host_url", "TEXT")]:
            try:
                db.execute(f"ALTER TABLE meeting ADD COLUMN {col} {decl}")
            except Exception:  # noqa: BLE001 - column already exists
                pass
        try:
            db.execute("ALTER TABLE account ADD COLUMN pw_hash TEXT")
        except Exception:  # noqa: BLE001 - column already exists
            pass


@contextmanager
def connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def recent_history(conv_id: int, limit: int = 5) -> list[dict]:
    """Last N turns for a conversation — the context every surface feeds the LLM."""
    with connect() as db:
        rows = db.execute(
            "SELECT role, content FROM message WHERE conv_id=? ORDER BY id DESC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_message(conv_id: int, role: str, content: str, action: str | None = None) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO message (conv_id, role, content, action) VALUES (?,?,?,?)",
            (conv_id, role, content, action),
        )
