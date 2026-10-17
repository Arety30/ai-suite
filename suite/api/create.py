"""Create routes — generate a document, slide deck, or spreadsheet locally and
download the resulting file."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from suite.core import create

router = APIRouter(prefix="/v1/create", tags=["create"])


class DocIn(BaseModel):
    user_id: int = 1
    title: str
    prompt: str
    format: str = "docx"   # docx | pdf | md
    doc_ids: list[int] | None = None   # ground the output in these vault sources


class SlidesIn(BaseModel):
    user_id: int = 1
    title: str
    prompt: str
    doc_ids: list[int] | None = None


class SheetIn(BaseModel):
    user_id: int = 1
    title: str
    prompt: str
    format: str = "xlsx"   # xlsx | csv
    doc_ids: list[int] | None = None


@router.post("/doc")
async def make_doc(body: DocIn):
    return await create.make_doc(body.user_id, body.title, body.prompt, body.format,
                                 body.doc_ids)


@router.post("/slides")
async def make_slides(body: SlidesIn):
    return await create.make_slides(body.user_id, body.title, body.prompt, body.doc_ids)


@router.post("/sheet")
async def make_sheet(body: SheetIn):
    return await create.make_sheet(body.user_id, body.title, body.prompt, body.format,
                                   body.doc_ids)


@router.get("/files")
async def list_files():
    return create.list_exports()


@router.get("/download/{name}")
async def download(name: str):
    path = (create.EXPORTS / name).resolve()
    if not str(path).startswith(str(create.EXPORTS.resolve())) or not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(path, filename=name)
