"""
FastAPI backend for the Context Compressor.

Run with:
    uvicorn main:app --reload --port 8000
"""

from typing import Dict, List, Literal, Optional

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env (e.g. GITHUB_TOKEN) into the process env, if present

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from context_compressor import ContextCompressor
from context_compressor.git_diff import compress_diff
from context_compressor.github_fetch import fetch_pr_diff_and_files, parse_pr_reference
from context_compressor.presets import PRESETS
from context_compressor.session_compressor import compress_session

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
    target_compression: Optional[float] = Field(None, ge=0.05, le=0.98,
        description="Overrides the preset's target if provided")
    content_type: Literal["auto", "code", "logs", "prose"] = "auto"
    preset: Optional[Literal["conservative", "balanced", "aggressive"]] = None
    model: Literal["default", "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini"] = "default"


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


def _run_compression(
    text: str,
    target_compression: Optional[float],
    content_type: str,
    preset: Optional[str] = None,
    model: str = "default",
) -> CompressResponse:
    if preset:
        overrides = {"model": model}
        if target_compression is not None:
            overrides["target_compression"] = target_compression
        compressor = ContextCompressor.from_preset(preset, **overrides)
    else:
        compressor = ContextCompressor(
            target_compression=target_compression if target_compression is not None else 0.70,
            model=model,
        )
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


class DiffCompressRequest(BaseModel):
    diff_text: str = Field(..., min_length=1, description="Raw unified diff, e.g. from `git diff` or a GitHub PR's .diff URL")
    file_contents: Dict[str, str] = Field(
        ..., description="Map of changed file path -> full NEW file content (post-change). "
                          "Keys should match the diff's '+++ b/...' paths (with or without the 'b/' prefix)."
    )
    target_compression: Optional[float] = Field(None, ge=0.05, le=0.98)
    model: Literal["default", "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini"] = "default"


class DiffFileReportOut(BaseModel):
    path: str
    original_tokens: int
    compressed_tokens: int
    compressed_text: str
    changed_blocks_kept: int
    context_blocks_kept: int
    dependency_blocks_restored: int
    blocks_total: int
    diff_lines: List[DiffLineOut]


class DiffCompressResponse(BaseModel):
    files: List[DiffFileReportOut]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    files_skipped: List[str]
    notes: List[str]


class GithubPrCompressRequest(BaseModel):
    pr: str = Field(
        ..., description="GitHub PR URL (https://github.com/owner/repo/pull/123) or shorthand owner/repo#123"
    )
    target_compression: Optional[float] = Field(None, ge=0.05, le=0.98)
    model: Literal["default", "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini"] = "default"


def _to_diff_response(report) -> DiffCompressResponse:
    return DiffCompressResponse(
        files=[
            DiffFileReportOut(
                path=f.path,
                original_tokens=f.original_tokens,
                compressed_tokens=f.compressed_tokens,
                compressed_text=f.compressed_text,
                changed_blocks_kept=f.changed_blocks_kept,
                context_blocks_kept=f.context_blocks_kept,
                dependency_blocks_restored=f.dependency_blocks_restored,
                blocks_total=f.blocks_total,
                diff_lines=[DiffLineOut(text=d.text, kept=d.kept) for d in f.diff_lines],
            )
            for f in report.files
        ],
        original_tokens=report.original_tokens,
        compressed_tokens=report.compressed_tokens,
        compression_ratio=report.compression_ratio,
        files_skipped=report.files_skipped,
        notes=report.notes,
    )


@app.post("/compress/diff", response_model=DiffCompressResponse)
def compress_diff_endpoint(req: DiffCompressRequest):
    """
    Diff-aware compression: given a unified diff plus the new content of
    each changed file, keep every block the diff actually touches, pull
    in whatever it depends on, and fill any remaining budget with the
    highest-value surrounding context. No git repo or GitHub access is
    needed server-side -- the caller supplies the diff and file contents
    (e.g. fetched from a GitHub PR's .diff URL and the repo checkout).
    """
    try:
        report = compress_diff(
            diff_text=req.diff_text,
            file_contents=req.file_contents,
            target_compression=req.target_compression if req.target_compression is not None else 0.70,
            model=req.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not report.files and not report.files_skipped:
        raise HTTPException(status_code=400, detail="diff_text contained no parseable file changes")

    return _to_diff_response(report)


@app.post("/compress/diff/github", response_model=DiffCompressResponse)
def compress_diff_github_endpoint(req: GithubPrCompressRequest):
    """
    Same as /compress/diff, but the server fetches the diff and file
    contents itself from a GitHub PR URL -- no OAuth, no connected
    account, just an unauthenticated (or GITHUB_TOKEN-authenticated)
    call to the public GitHub REST API. Only works for PRs the server
    can read anonymously (public repos), unless GITHUB_TOKEN is set in
    its environment.
    """
    try:
        owner, repo, pr_number = parse_pr_reference(req.pr)
        diff_text, file_contents = fetch_pr_diff_and_files(owner, repo, pr_number)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        report = compress_diff(
            diff_text=diff_text,
            file_contents=file_contents,
            target_compression=req.target_compression if req.target_compression is not None else 0.70,
            model=req.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not report.files and not report.files_skipped:
        raise HTTPException(status_code=400, detail="PR diff contained no parseable file changes")

    return _to_diff_response(report)


class TokenizeRequest(BaseModel):
    text: str = Field("", description="Text to count tokens for (may be empty)")
    model: Literal["default", "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini"] = "default"


class TokenizeResponse(BaseModel):
    tokens: int


@app.post("/tokenize", response_model=TokenizeResponse)
def tokenize(req: TokenizeRequest):
    """
    Cheap token-count-only endpoint (no compression run) so the frontend
    can show a live "~N tokens" counter while the user is still typing/
    pasting, without paying the cost of the full compression pipeline.
    """
    from context_compressor.tokenizer import count_tokens

    return TokenizeResponse(tokens=count_tokens(req.text, req.model))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/presets")
def list_presets():
    return {
        name: {
            "target_compression": p.target_compression,
            "dedup_threshold": p.dedup_threshold,
            "min_accuracy_floor": p.min_accuracy_floor,
            "description": p.description,
        }
        for name, p in PRESETS.items()
    }


@app.post("/compress", response_model=CompressResponse)
def compress(req: CompressRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")
    return _run_compression(req.text, req.target_compression, req.content_type, req.preset, req.model)


@app.post("/compress/file", response_model=CompressResponse)
async def compress_file(
    file: UploadFile = File(...),
    target_compression: Optional[float] = None,
    content_type: Optional[str] = "auto",
    preset: Optional[str] = None,
    model: str = "default",
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file must be UTF-8 text")
    if not text.strip():
        raise HTTPException(status_code=400, detail="file is empty")
    return _run_compression(text, target_compression, content_type or "auto", preset, model)


class SessionCompressRequest(BaseModel):
    export: str = Field(
        ..., min_length=1,
        description="Raw JSON text of a ChatGPT conversations.json export, a claude.ai "
                    "conversation export, or a generic [{'role': ..., 'content': ...}, ...] list",
    )
    protect_recent: int = Field(4, ge=0, le=100,
        description="Number of most-recent turns to always keep verbatim, in addition to any system prompt")
    target_compression: float = Field(0.70, ge=0.05, le=0.98,
        description="Fraction of tokens to remove from each compressible (older) turn")
    model: Literal["default", "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini"] = "default"
    dedup_threshold: Optional[float] = Field(0.9, ge=0.0, le=1.0,
        description="Cosine-similarity cutoff for dropping duplicate older turns; omit/null for adaptive")


class SessionTurnOut(BaseModel):
    role: str
    original_tokens: int
    compressed_tokens: int
    action: str
    content: str


class SessionCompressResponse(BaseModel):
    turns: List[SessionTurnOut]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    turns_total: int
    turns_kept: int
    turns_dropped_duplicate: int
    notes: List[str]


@app.post("/compress/session", response_model=SessionCompressResponse)
def compress_session_endpoint(req: SessionCompressRequest):
    """
    Compress a chat/conversation export: the system prompt and the most
    recent `protect_recent` turns are kept verbatim, near-duplicate
    older turns are dropped, and every other older turn is run through
    the normal compression pipeline. Useful for trimming long ChatGPT/
    Claude/agent conversation histories before re-feeding them as
    context (the "hermes"-style compaction use case).
    """
    try:
        report = compress_session(
            raw_export=req.export,
            protect_recent=req.protect_recent,
            target_compression=req.target_compression,
            model=req.model,
            dedup_threshold=req.dedup_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SessionCompressResponse(
        turns=[
            SessionTurnOut(
                role=t.role,
                original_tokens=t.original_tokens,
                compressed_tokens=t.compressed_tokens,
                action=t.action,
                content=t.content,
            )
            for t in report.turns
        ],
        original_tokens=report.original_tokens,
        compressed_tokens=report.compressed_tokens,
        compression_ratio=report.compression_ratio,
        turns_total=report.turns_total,
        turns_kept=report.turns_kept,
        turns_dropped_duplicate=report.turns_dropped_duplicate,
        notes=report.notes,
    )