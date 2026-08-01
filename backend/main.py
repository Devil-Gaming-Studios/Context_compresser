"""
FastAPI backend for the Context Compressor.

Run with:
    uvicorn main:app --reload --port 8000
"""

from typing import List, Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from context_compressor import ContextCompressor

app = FastAPI(title="Context Compressor API", version="1.0.0")

# Allow the local Vite dev server (and any origin during local hackathon
# demos) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompressRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text to compress")
    target_compression: float = Field(0.70, ge=0.05, le=0.98)
    content_type: Literal["auto", "code", "logs", "prose"] = "auto"


class DiffLineOut(BaseModel):
    text: str
    kept: bool


class CompressResponse(BaseModel):
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    chunks_total: int
    chunks_kept: int
    near_duplicates_removed: int
    structural_lines_collapsed: int
    compressed_text: str
    notes: List[str]
    diff_lines: List[DiffLineOut]


def _run_compression(text: str, target_compression: float, content_type: str) -> CompressResponse:
    compressor = ContextCompressor(target_compression=target_compression)
    report = compressor.compress(text, content_type=content_type)
    return CompressResponse(
        original_tokens=report.original_tokens,
        compressed_tokens=report.compressed_tokens,
        compression_ratio=report.compression_ratio,
        chunks_total=report.chunks_total,
        chunks_kept=report.chunks_kept,
        near_duplicates_removed=report.near_duplicates_removed,
        structural_lines_collapsed=report.structural_lines_collapsed,
        compressed_text=report.compressed_text,
        notes=report.notes,
        diff_lines=[DiffLineOut(text=d.text, kept=d.kept) for d in report.diff_lines],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/compress", response_model=CompressResponse)
def compress(req: CompressRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")
    return _run_compression(req.text, req.target_compression, req.content_type)


@app.post("/compress/file", response_model=CompressResponse)
async def compress_file(
    file: UploadFile = File(...),
    target_compression: float = 0.70,
    content_type: Optional[str] = "auto",
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file must be UTF-8 text")
    if not text.strip():
        raise HTTPException(status_code=400, detail="file is empty")
    return _run_compression(text, target_compression, content_type or "auto")
