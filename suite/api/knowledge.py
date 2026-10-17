"""Knowledge routes: documents/RAG, study generation, notes + graph."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from suite.core import documents, notes

router = APIRouter(prefix="/v1", tags=["knowledge"])


# ---- documents / RAG --------------------------------------------------------

class DocIn(BaseModel):
    user_id: int = 1
    title: str
    text: str
    category: str = "note"
    source: str = "manual"


@router.post("/docs")
async def add_doc(body: DocIn):
    return await documents.ingest_document(
        body.user_id, body.title, body.text, body.category, body.source
    )


class AskIn(BaseModel):
    user_id: int = 1
    question: str
    doc_ids: list[int] | None = None


@router.post("/docs/ask")
async def ask(body: AskIn):
    return await documents.rag_ask(body.user_id, body.question, body.doc_ids)


class StudyIn(BaseModel):
    user_id: int = 1
    kind: str  # guide | flashcards | quiz
    doc_ids: list[int]


@router.post("/study/generate")
async def study(body: StudyIn):
    return await documents.generate_study(body.user_id, body.kind, body.doc_ids)


# ---- notes / graph ----------------------------------------------------------

class NoteIn(BaseModel):
    user_id: int = 1
    title: str
    body: str
    tags: list[str] | None = None


@router.post("/notes")
async def create_note(body: NoteIn):
    from suite.core import vault
    result = notes.create_note(body.user_id, body.title, body.body, body.tags)
    await vault.index_content(body.user_id, "note", result["id"], body.title, body.body)
    return result


@router.get("/notes/graph")
async def note_graph(user_id: int = 1):
    return notes.graph(user_id)


@router.get("/notes/backlinks")
async def note_backlinks(title: str, user_id: int = 1):
    return {"backlinks": notes.backlinks(user_id, title)}


# ---- extended routes for frontend integration -----------------------------
from suite.core import memory
import json

class NoteUpdateIn(BaseModel):
    body: str

@router.get("/notes")
async def list_notes(user_id: int = 1):
    with memory.connect() as db:
        rows = db.execute(
            "SELECT id, title, body, tags, links, updated FROM note WHERE user_id=? ORDER BY updated DESC",
            (user_id,)
        ).fetchall()
    return [{
        "id": r["id"],
        "title": r["title"],
        "body": r["body"],
        "tags": json.loads(r["tags"]),
        "links": json.loads(r["links"]),
        "updated": r["updated"]
    } for r in rows]

@router.put("/notes/{note_id}")
async def update_note_route(note_id: int, body: NoteUpdateIn):
    # Calling the core update_note function which parses backlinks and links automatically!
    from suite.core import vault
    result = notes.update_note(note_id, body.body)
    with memory.connect() as db:
        row = db.execute("SELECT user_id, title FROM note WHERE id=?", (note_id,)).fetchone()
    if row:  # keep the vault index in sync with the edited body
        await vault.index_content(row["user_id"], "note", note_id, row["title"], body.body)
    return result

@router.delete("/notes/{note_id}")
async def delete_note_route(note_id: int):
    with memory.connect() as db:
        db.execute("DELETE FROM note WHERE id=?", (note_id,))
        db.execute("DELETE FROM vault_chunk WHERE kind='note' AND ref_id=?", (note_id,))
    return {"ok": True}

@router.get("/docs")
async def list_docs(user_id: int = 1):
    with memory.connect() as db:
        rows = db.execute(
            "SELECT id, title, source, category, text FROM document WHERE user_id=?",
            (user_id,)
        ).fetchall()
    return [{
        "id": r["id"],
        "title": r["title"],
        "source": r["source"],
        "category": r["category"],
        "text": r["text"]
    } for r in rows]

@router.delete("/docs/{doc_id}")
async def delete_doc_route(doc_id: int):
    with memory.connect() as db:
        db.execute("DELETE FROM document WHERE id=?", (doc_id,))
        db.execute("DELETE FROM chunk WHERE doc_id=?", (doc_id,))
        db.execute("DELETE FROM vault_chunk WHERE kind='doc' AND ref_id=?", (doc_id,))
    return {"ok": True}



@router.post("/docs/upload")
async def upload_doc(file: UploadFile, user_id: int = 1, title: str | None = None):
    """Upload a PDF/docx/txt file — its text is extracted and ingested into the Vault."""
    data = await file.read()
    text = documents.extract_text(file.filename or "upload", data)
    if not text.strip():
        raise HTTPException(400, "no extractable text in that file")
    result = await documents.ingest_document(
        user_id, title or (file.filename or "Uploaded document"), text,
        category="upload", source=file.filename or "upload")
    return {**result, "title": title or file.filename, "chars": len(text)}
