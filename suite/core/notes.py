"""Notes with wiki-links, backlinks and a knowledge graph.

Ported from meeting-and-study-room-hub/ObsidianWorkspace.tsx — the graph physics
belong in the front end, but link parsing, backlinks and graph *data* belong here
so every surface (web, desktop, CLI) shares one source of truth.
"""
from __future__ import annotations

import json
import re

from suite.core import memory

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _links_in(body: str) -> list[str]:
    return sorted({m.strip() for m in WIKILINK_RE.findall(body)})


def create_note(user_id: int, title: str, body: str,
                tags: list[str] | None = None) -> dict:
    links = _links_in(body)
    with memory.connect() as db:
        cur = db.execute(
            "INSERT INTO note (user_id, title, body, tags, links) VALUES (?,?,?,?,?)",
            (user_id, title, body, json.dumps(tags or []), json.dumps(links)),
        )
    return {"id": cur.lastrowid, "title": title, "links": links, "tags": tags or []}


def update_note(note_id: int, body: str) -> dict:
    links = _links_in(body)
    with memory.connect() as db:
        db.execute(
            "UPDATE note SET body=?, links=?, updated=CURRENT_TIMESTAMP WHERE id=?",
            (body, json.dumps(links), note_id),
        )
    return {"id": note_id, "links": links}


def backlinks(user_id: int, title: str) -> list[dict]:
    """Notes whose body links to `title` via [[title]]."""
    with memory.connect() as db:
        rows = db.execute(
            "SELECT id, title, links FROM note WHERE user_id=?", (user_id,)
        ).fetchall()
    return [{"id": r["id"], "title": r["title"]}
            for r in rows if title in json.loads(r["links"])]


def graph(user_id: int) -> dict:
    """Nodes = notes + meetings; edges = resolved [[wiki-links]] between note titles."""
    with memory.connect() as db:
        notes = db.execute(
            "SELECT id, title, links, tags FROM note WHERE user_id=?", (user_id,)
        ).fetchall()
        meetings = db.execute(
            "SELECT id, title FROM meeting WHERE user_id=?", (user_id,)
        ).fetchall()
    title_to_id = {n["title"]: f"note:{n['id']}" for n in notes}
    nodes = [{"id": f"note:{n['id']}", "label": n["title"], "type": "note",
              "tags": json.loads(n["tags"])} for n in notes]
    nodes += [{"id": f"meeting:{m['id']}", "label": m["title"], "type": "meeting"}
              for m in meetings]
    edges = []
    for n in notes:
        src = f"note:{n['id']}"
        for target_title in json.loads(n["links"]):
            if target_title in title_to_id:
                edges.append({"source": src, "target": title_to_id[target_title]})
    return {"nodes": nodes, "edges": edges}
