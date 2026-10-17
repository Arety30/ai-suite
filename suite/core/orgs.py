"""Organizations & accounts.

An organization is a school or a company; it gets an 18-char id. Accounts are
individual people; a normal user is just an account with no org (no student/normal
classification), while a school's students or a company's staff are accounts that
belong to an org. Meeting join codes derive from these ids (see identity.py).
"""
from __future__ import annotations

from suite.core import identity, memory

ORG_TYPES = ("school", "company")


def create_org(name: str, org_type: str) -> dict:
    if org_type not in ORG_TYPES:
        org_type = "company"
    oid = identity.generate_id()
    with memory.connect() as db:
        db.execute("INSERT INTO organization (id, name, type) VALUES (?,?,?)",
                   (oid, name, org_type))
    return {"id": oid, "name": name, "type": org_type}


def get_org(org_id: str) -> dict | None:
    with memory.connect() as db:
        r = db.execute("SELECT id, name, type, created FROM organization WHERE id=?",
                       (org_id,)).fetchone()
    return dict(r) if r else None


def list_orgs() -> list[dict]:
    with memory.connect() as db:
        rows = db.execute("SELECT id, name, type, created FROM organization "
                          "ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


def create_account(name: str, org_id: str | None = None) -> dict:
    aid = identity.generate_id()
    with memory.connect() as db:
        db.execute("INSERT INTO account (id, name, org_id) VALUES (?,?,?)",
                   (aid, name, org_id))
    return {"id": aid, "name": name, "org_id": org_id}


def get_account(account_id: str) -> dict | None:
    with memory.connect() as db:
        r = db.execute("SELECT id, name, org_id, created FROM account WHERE id=?",
                       (account_id,)).fetchone()
    return dict(r) if r else None


def org_members(org_id: str) -> list[dict]:
    with memory.connect() as db:
        rows = db.execute("SELECT id, name FROM account WHERE org_id=?",
                          (org_id,)).fetchall()
    return [dict(r) for r in rows]
