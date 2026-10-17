"""Documents + RAG + study generation.

Ported from meeting-and-study-room-hub (server.ts, NotebookLM.tsx, NotesPanel.tsx)
and the Antigravity quiz sessions — but real, not the "fake local model" theater:
it genuinely embeds with a local Ollama model and retrieves before answering.
"""
from __future__ import annotations

import json
import math
import re

from suite.core import memory
from suite.providers.base import registry


# ---- chunking + similarity (pure, testable, no providers needed) ------------

def chunk_text(text: str, *, size: int = 800, overlap: int = 120) -> list[str]:
    """Split on paragraph boundaries, packing up to ~size chars per chunk."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            # a single oversized paragraph is hard-split with overlap
            if len(p) > size:
                for i in range(0, len(p), size - overlap):
                    chunks.append(p[i:i + size])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks or [text[:size]]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---- ingestion + retrieval --------------------------------------------------

async def ingest_document(user_id: int, title: str, text: str,
                          category: str = "note", source: str = "manual") -> dict:
    with memory.connect() as db:
        cur = db.execute(
            "INSERT INTO document (user_id, title, source, category, text) VALUES (?,?,?,?,?)",
            (user_id, title, source, category, text),
        )
        doc_id = cur.lastrowid
    # Index into the shared vault so notes-and-sources retrieval spans this doc.
    from suite.core import vault  # lazy: avoids import cycle
    n = await vault.index_content(user_id, "doc", doc_id, title, text)
    return {"document_id": doc_id, "chunks": n}


async def retrieve(user_id: int, query: str, *, k: int = 5,
                   doc_ids: list[int] | None = None) -> list[dict]:
    """Docs-only retrieval, via the shared vault index."""
    from suite.core import vault  # lazy
    hits = await vault.search_chunks(user_id, query, k=k, kinds=["doc"])
    return [{"text": h["text"], "doc_id": h["ref_id"], "title": h["title"],
             "score": h["score"]} for h in hits]


# ---- question answering + study artifacts -----------------------------------

async def rag_ask(user_id: int, question: str,
                  doc_ids: list[int] | None = None) -> dict:
    hits = await retrieve(user_id, question, doc_ids=doc_ids)
    context = "\n\n".join(f"[{h['title']}] {h['text']}" for h in hits)
    prompt = [
        {"role": "system", "content": "Answer using ONLY the sources. Cite titles in "
                                       "[brackets]. If the sources don't cover it, say so."},
        {"role": "user", "content": f"Sources:\n{context}\n\nQuestion: {question}"},
    ]
    reply = await registry.call("llm", "chat", prompt)
    return {"answer": reply.text,
            "sources": [{"doc_id": h["doc_id"], "title": h["title"]} for h in hits]}


_STUDY_PROMPTS = {
    "guide": "Produce a concise markdown study guide (headings + bullets) from the material.",
    "flashcards": ('Create 8-12 study flashcards from the material. Respond with a JSON '
                   'object of the form {"items": [{"question": "...", "answer": "..."}]}.'),
    "quiz": ('Create 5-8 multiple-choice questions from the material. Respond with a JSON '
             'object {"items": [{"question": "...", "options": ["a","b","c","d"], '
             '"answer_index": 0}]}.'),
}


async def generate_study(user_id: int, kind: str, doc_ids: list[int]) -> dict:
    with memory.connect() as db:
        marks = ",".join("?" * len(doc_ids))
        rows = db.execute(
            f"SELECT text FROM document WHERE user_id=? AND id IN ({marks})",
            [user_id, *doc_ids],
        ).fetchall()
    material = "\n\n".join(r["text"] for r in rows)
    return await generate_study_from_material(kind, material)


async def generate_study_from_material(kind: str, material: str) -> dict:
    """Generate a study guide / flashcards / quiz from raw text (docs or a meeting
    transcript). Shared by the Study app and Student meetings."""
    if kind not in _STUDY_PROMPTS:
        raise ValueError(f"kind must be one of {list(_STUDY_PROMPTS)}")
    prompt = [
        {"role": "system", "content": _STUDY_PROMPTS[kind]},
        {"role": "user", "content": material[:8000]},
    ]
    if kind == "guide":
        reply = await registry.call("llm", "chat", prompt)
        return {"kind": kind, "markdown": reply.text}
    # Force JSON mode for structured artifacts so small local models stay parseable.
    reply = await registry.call("llm", "chat", prompt, format="json")
    return {"kind": kind, "items": _parse_json_items(reply.text)}


def _parse_json_items(text: str) -> list:
    """Extract a list of items from an LLM reply. Handles a bare array, an object
    wrapping the array under a common key, or JSON fenced/embedded in prose."""
    candidate = text.strip()
    # try whole reply first (json-mode returns clean JSON)
    for attempt in (candidate, _first_json_block(candidate)):
        if not attempt:
            continue
        try:
            data = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "cards", "flashcards", "questions", "quiz"):
                if isinstance(data.get(key), list):
                    return data[key]
            # single object or {k: [...]} with an unknown key
            for val in data.values():
                if isinstance(val, list):
                    return val
    return []


def _first_json_block(text: str) -> str | None:
    m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    return m.group(0) if m else None


def extract_text(filename: str, data: bytes) -> str:
    """Pull plain text out of an uploaded file (PDF / docx / txt / md). Local only."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    import io
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if ext == "docx":
        from docx import Document as _Docx
        doc = _Docx(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    # txt, md, csv, or anything text-ish
    return data.decode("utf-8", errors="replace").strip()
