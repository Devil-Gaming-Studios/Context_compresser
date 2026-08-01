"""
Multi-file / repository compression.

Compressing files one at a time is blind to cross-file structure: a
helper defined in utils.py might look like low-value filler in
isolation, but if three other files in the same repo import and call
it, dropping it breaks all of them. This module:

  1. Builds a repo-wide symbol table (definitions per file) using the
     same AST/indentation block chunker as single-file compression.
  2. Compresses each file's blocks against a *shared* token budget
     (proportional to each file's share of the total input) instead of
     each file getting the same reduction target regardless of size.
  3. Runs a cross-file dependency closure pass: if a kept block in
     file A calls a symbol defined in file B, file B's defining block
     is force-kept even if file B's own local budget would have
     dropped it.

This is a heuristic multi-file extension, not a real cross-module
resolver (it doesn't track import aliasing, `from x import *`, etc.)
-- it catches the common case of "helper defined in one file, used in
another with the same top-level name."
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .code_chunker import build_symbol_table, chunk_code_by_indentation, chunk_python_by_block
from .compressor import ContextCompressor, DiffLine
from .scoring import score_chunks
from .tokenizer import count_tokens

DEFAULT_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rs", ".php", ".kt", ".swift",
}


@dataclass
class FileReport:
    path: str
    original_tokens: int
    compressed_tokens: int
    compressed_text: str
    diff_lines: List[DiffLine] = field(default_factory=list)


@dataclass
class RepoCompressionReport:
    files: List[FileReport]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    cross_file_symbols_restored: int
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.files)} files, {self.original_tokens} -> {self.compressed_tokens} tokens "
            f"({self.compression_ratio * 100:.1f}% reduction), "
            f"{self.cross_file_symbols_restored} cross-file symbol(s) restored"
        )


def collect_files(root: str, extensions: Optional[Sequence[str]] = None, max_files: int = 500) -> List[str]:
    """Walk `root` and return paths to source files with a matching
    extension, skipping common noise directories."""
    exts = set(extensions) if extensions else DEFAULT_CODE_EXTENSIONS
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for fn in filenames:
            if os.path.splitext(fn)[1] in exts:
                found.append(os.path.join(dirpath, fn))
                if len(found) >= max_files:
                    return found
    return found


def compress_repo(
    root: str,
    target_compression: float = 0.70,
    extensions: Optional[Sequence[str]] = None,
    model: str = "default",
) -> RepoCompressionReport:
    """
    Compress every source file under `root` against a shared token
    budget, with a cross-file dependency-closure pass so a definition
    used elsewhere in the repo survives even if it looked low-value in
    its own file.
    """
    paths = collect_files(root, extensions)
    notes = [f"scanned {len(paths)} files under {root}"]

    file_texts: Dict[str, str] = {}
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                file_texts[p] = f.read()
        except OSError:
            continue

    # Per-file block chunking + a combined symbol table keyed by
    # (path, block_index) so we can trace cross-file references.
    file_blocks: Dict[str, list] = {}
    global_symbol_table: Dict[str, tuple] = {}  # name -> (path, block_idx)
    for p, text in file_texts.items():
        blocks = chunk_python_by_block(text) if p.endswith(".py") else None
        if blocks is None:
            blocks = chunk_code_by_indentation(text)
        file_blocks[p] = blocks
        local_table = build_symbol_table(blocks)
        for name, idx in local_table.items():
            global_symbol_table[name] = (p, idx)

    total_original = sum(count_tokens(t, model=model) for t in file_texts.values())
    if total_original == 0:
        return RepoCompressionReport([], 0, 0, 0.0, 0, notes=["no files found"])

    keep_masks: Dict[str, list] = {}
    scores_by_file: Dict[str, list] = {}

    for p, blocks in file_blocks.items():
        chunk_texts = [b.text for b in blocks]
        scores = score_chunks(chunk_texts) if chunk_texts else []
        scores_by_file[p] = scores

        file_tokens = count_tokens(file_texts[p], model=model)
        share = file_tokens / total_original if total_original else 0
        file_budget = max(1, round(share * total_original * (1 - target_compression)))

        order = sorted(range(len(chunk_texts)), key=lambda i: scores[i], reverse=True)
        mask = [False] * len(chunk_texts)
        running = 0
        kept = 0
        for idx in order:
            t = count_tokens(chunk_texts[idx], model=model)
            if running + t > file_budget and kept > 0:
                continue
            mask[idx] = True
            running += t
            kept += 1
        keep_masks[p] = mask

    # Cross-file dependency closure.
    restored = 0
    changed = True
    while changed:
        changed = False
        for p, blocks in file_blocks.items():
            mask = keep_masks[p]
            for i, b in enumerate(blocks):
                if not mask[i]:
                    continue
                for ref in b.references:
                    loc = global_symbol_table.get(ref)
                    if loc is None:
                        continue
                    ref_path, ref_idx = loc
                    if ref_path == p and ref_idx == i:
                        continue
                    if not keep_masks[ref_path][ref_idx]:
                        keep_masks[ref_path][ref_idx] = True
                        restored += 1
                        changed = True
    if restored:
        notes.append(f"cross-file dependency closure restored {restored} block(s)")

    file_reports = []
    total_compressed = 0
    for p, blocks in file_blocks.items():
        mask = keep_masks[p]
        kept_texts = [b.text for b, k in zip(blocks, mask) if k]
        compressed_text = "\n\n".join(kept_texts)
        orig_tok = count_tokens(file_texts[p], model=model)
        comp_tok = count_tokens(compressed_text, model=model)
        if comp_tok >= orig_tok:
            compressed_text = file_texts[p]
            comp_tok = orig_tok
        total_compressed += comp_tok
        diff_lines = [DiffLine(text=b.text, kept=k) for b, k in zip(blocks, mask)]
        file_reports.append(FileReport(
            path=p,
            original_tokens=orig_tok,
            compressed_tokens=comp_tok,
            compressed_text=compressed_text,
            diff_lines=diff_lines,
        ))

    ratio = 1 - (total_compressed / total_original) if total_original else 0.0
    return RepoCompressionReport(
        files=file_reports,
        original_tokens=total_original,
        compressed_tokens=total_compressed,
        compression_ratio=ratio,
        cross_file_symbols_restored=restored,
        notes=notes,
    )
