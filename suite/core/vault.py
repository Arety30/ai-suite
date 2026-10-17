"""The vault: Obsidian x NotebookLM.

Notes and documents share ONE embedding index (vault_chunk) and ONE graph. That
single decision is the whole feature:

  ask()          -> RAG grounded in notes AND sources together, typed citations
  graph()        -> notes + sources as nodes; explicit [[wiki-links]] + semantic edges
  suggest_links()-> related notes/sources by meaning (auto-links Obsidian can't make)

All local: embeddings via the Ollama `embed` provider, retrieval by cosine in SQLite.
"""
from __future__ import annotations

import json
from collections import defaultdict

from suite.core import memory
from suite.core.documents import chunk_text, cosine  # pure helpers, no cycle
from suite.providers.base import registry

SIM_THRESHOLD = 0.72   # cosine above this becomes a "related" edge in the graph
_LABEL = {"note": "Note", "doc": "Source"}


async def _embed(text: str) -> list[float]:
    return await registry.call("embed", "embed", text)


# ---- indexing (called whenever a note or document is written) ---------------

async def index_content(user_id: int, kind: str, ref_id: int, title: str, text: str) -> int:
    """(Re)index one note or document into the shared vault. Returns chunk count."""
    chunks = chunk_text(text)
    vectors = [await _embed(c) for c in chunks]
    with memory.connect() as db:
        db.execute("DELETE FROM vault_chunk WHERE user_id=? AND kind=? AND ref_id=?",
                   (user_id, kind, ref_id))
        for i, (ch, vec) in enumerate(zip(chunks, vectors)):
            db.execute(
                "INSERT INTO vault_chunk (user_id, kind, ref_id, title, ordinal, text, embedding) "
                "VALUES (?,?,?,?,?,?,?)",
                (user_id, kind, ref_id, title, i, ch, json.dumps(vec)),
            )
    return len(chunks)


def deindex(user_id: int, kind: str, ref_id: int) -> None:
    with memory.connect() as db:
        db.execute("DELETE FROM vault_chunk WHERE user_id=? AND kind=? AND ref_id=?",
                   (user_id, kind, ref_id))


# ---- retrieval --------------------------------------------------------------

async def search_chunks(user_id: int, query: str, *, k: int = 6,
                        kinds: list[str] | None = None) -> list[dict]:
    qvec = await _embed(query)
    sql = "SELECT kind, ref_id, title, text, embedding FROM vault_chunk WHERE user_id=?"
    params: list = [user_id]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params += kinds
    with memory.connect() as db:
        rows = db.execute(sql, params).fetchall()
    scored = [{"kind": r["kind"], "ref_id": r["ref_id"], "title": r["title"],
               "text": r["text"], "score": cosine(qvec, json.loads(r["embedding"]))}
              for r in rows]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


async def ask(user_id: int, question: str, *, kinds: list[str] | None = None) -> dict:
    """Answer grounded in the vault. Citations mark each source as Note or Source."""
    hits = await search_chunks(user_id, question, k=6, kinds=kinds)
    if not hits:
        return {"answer": "Nothing in your vault yet — add a note or a source first.",
                "sources": []}
    context = "\n\n".join(f"[{_LABEL[h['kind']]}: {h['title']}] {h['text']}" for h in hits)
    prompt = [
        {"role": "system", "content":
            "Answer using ONLY the provided context, which mixes the user's own NOTES "
            "and their SOURCES. Cite titles in [brackets]. If it isn't covered, say so."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    reply = await registry.call("llm", "chat", prompt)
    seen, sources = set(), []
    for h in hits:
        key = (h["kind"], h["ref_id"])
        if key not in seen:
            seen.add(key)
            sources.append({"kind": h["kind"], "ref_id": h["ref_id"], "title": h["title"]})
    return {"answer": reply.text, "sources": sources}


# ---- node-level vectors (average of a node's chunks), for graph + suggest ----

def _node_vectors(user_id: int) -> dict[tuple, dict]:
    with memory.connect() as db:
        rows = db.execute(
            "SELECT kind, ref_id, title, embedding FROM vault_chunk WHERE user_id=?",
            (user_id,)).fetchall()
    acc: dict[tuple, list] = defaultdict(list)
    titles: dict[tuple, str] = {}
    for r in rows:
        key = (r["kind"], r["ref_id"])
        acc[key].append(json.loads(r["embedding"]))
        titles[key] = r["title"]
    nodes = {}
    for key, vecs in acc.items():
        dim = len(vecs[0])
        avg = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        nodes[key] = {"title": titles[key], "vec": avg}
    return nodes


def suggest_links(user_id: int, note_id: int, *, k: int = 5) -> list[dict]:
    """Related notes/sources by meaning, excluding ones already wiki-linked."""
    nodes = _node_vectors(user_id)
    target = nodes.get(("note", note_id))
    if not target:
        return []
    with memory.connect() as db:
        row = db.execute("SELECT links FROM note WHERE id=?", (note_id,)).fetchone()
    already = set(json.loads(row["links"])) if row and row["links"] else set()
    ranked = []
    for (kind, ref_id), n in nodes.items():
        if (kind, ref_id) == ("note", note_id) or n["title"] in already:
            continue
        ranked.append({"kind": kind, "ref_id": ref_id, "title": n["title"],
                       "score": round(cosine(target["vec"], n["vec"]), 3)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:k]


def graph(user_id: int, *, sim_threshold: float = SIM_THRESHOLD) -> dict:
    """Unified graph. Nodes = notes + sources. Edges: explicit [[wiki-links]]
    (solid) plus semantic-similarity edges (related) above the threshold."""
    nodes = _node_vectors(user_id)
    title_to_key = {n["title"]: key for key, n in nodes.items()}
    out_nodes = [{"id": f"{k}:{rid}", "label": n["title"], "type": k}
                 for (k, rid), n in nodes.items()]

    edges = []
    # explicit wiki-links from notes -> any node with that title
    with memory.connect() as db:
        note_rows = db.execute(
            "SELECT id, links FROM note WHERE user_id=?", (user_id,)).fetchall()
    for r in note_rows:
        src = f"note:{r['id']}"
        for target_title in json.loads(r["links"] or "[]"):
            tgt = title_to_key.get(target_title)
            if tgt:
                edges.append({"source": src, "target": f"{tgt[0]}:{tgt[1]}",
                              "type": "link"})
    # semantic edges (undirected, dedup by pair)
    keys = list(nodes)
    seen_pairs = set()
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            sim = cosine(nodes[a]["vec"], nodes[b]["vec"])
            if sim >= sim_threshold:
                pair = tuple(sorted([f"{a[0]}:{a[1]}", f"{b[0]}:{b[1]}"]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    edges.append({"source": pair[0], "target": pair[1],
                                  "type": "related", "weight": round(sim, 3)})
    return {"nodes": out_nodes, "edges": edges}
