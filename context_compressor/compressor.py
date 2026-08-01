"""
ContextCompressor -- the main entry point.

Pipeline:
  1. Structural boilerplate strip (blank-line runs, near-identical
     repeated lines, and -- for logs -- repeated multi-line blocks like
     a recurring stack trace)
  2. Chunking:
       - code: AST-based logical blocks (functions/classes) when the
         source parses as Python, indentation-based blocks otherwise,
         falling back to line-level if neither applies
       - logs: line-level
       - prose: sentence-level
  3. Semantic near-duplicate removal (TF-IDF cosine similarity, with
     an optional adaptive per-document threshold)
  4. Information-density scoring (TF-IDF mass per chunk), with a
     dependency-closure pass for code that force-keeps any block whose
     symbol is still referenced by another kept block
  5. Budget-constrained selection: keep the highest-scoring chunks,
     in original order, until the token budget is met
"""

import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Sequence

import numpy as np

from .boilerplate import strip_structural_boilerplate
from .code_chunker import (
    CodeBlock,
    build_symbol_table,
    chunk_code_by_indentation,
    chunk_python_by_block,
    dependency_closure,
)
from .dedup import remove_near_duplicates
from .presets import Preset, get_preset
from .scoring import score_chunks
from .tokenizer import count_tokens

ContentType = Literal["auto", "code", "logs", "prose"]


@dataclass
class DiffLine:
    text: str
    kept: bool


@dataclass
class CompressionReport:
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float          # e.g. 0.72 means 72% smaller
    chunks_total: int
    chunks_kept: int
    near_duplicates_removed: int
    structural_lines_collapsed: int
    compressed_text: str
    notes: List[str] = field(default_factory=list)
    diff_lines: List[DiffLine] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.original_tokens} -> {self.compressed_tokens} tokens "
            f"({self.compression_ratio * 100:.1f}% reduction), "
            f"{self.chunks_kept}/{self.chunks_total} chunks kept, "
            f"{self.near_duplicates_removed} near-duplicates removed, "
            f"{self.structural_lines_collapsed} repeated lines collapsed"
        )


def _detect_content_type(text: str) -> ContentType:
    code_signals = len(
        re.findall(r"^\s*(def |class |import |function |const |let |var |#include)", text, re.MULTILINE)
    )
    log_signals = len(
        re.findall(r"^\s*\[?\d{4}-\d{2}-\d{2}|^\s*(INFO|DEBUG|WARN|ERROR)\b", text, re.MULTILINE)
    )
    if log_signals > code_signals and log_signals > 2:
        return "logs"
    if code_signals > 2:
        return "code"
    return "prose"


def _chunk_code(text: str, use_code_blocks: bool):
    """
    Returns (chunks, blocks_or_none). blocks_or_none is the list of
    CodeBlock objects (with symbol info) when block-based chunking was
    used, or None when we fell back to plain line splitting -- callers
    use that to decide whether a dependency-closure pass is possible.
    """
    if not use_code_blocks:
        return text.splitlines(), None

    blocks = chunk_python_by_block(text)
    if blocks is None:
        blocks = chunk_code_by_indentation(text)
    if not blocks:
        return text.splitlines(), None
    return [b.text for b in blocks], blocks


def _chunk_text(text: str, content_type: ContentType) -> List[str]:
    if content_type == "logs":
        return text.splitlines()
    if content_type == "code":
        return text.splitlines()
    # prose: split on sentence boundaries, keep it simple/dependency-free
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    lines = [l for l in text.splitlines() if l.strip()]
    # If there's no real sentence punctuation (so the "sentence split"
    # just returned the whole blob as one chunk) but the text has
    # multiple lines, fall back to line-level chunking -- otherwise a
    # single indivisible chunk can't be trimmed at all, defeating the
    # point of compression.
    if len(sentences) <= 1 and len(lines) > 1:
        return lines
    return sentences


def _join_chunks(chunks: List[str], content_type: ContentType) -> str:
    if content_type in ("code", "logs"):
        return "\n".join(chunks)
    return " ".join(chunks)


class ContextCompressor:
    def __init__(
        self,
        target_compression: float = 0.70,
        min_accuracy_floor: float = 0.95,
        dedup_threshold: Optional[float] = 0.85,
        extra_filler_patterns: Optional[Sequence[str]] = None,
        use_code_blocks: bool = True,
        model: str = "default",
        summarize_log_blocks: bool = True,
    ):
        """
        target_compression: fraction of tokens to remove (0.70 = keep ~30%)
        min_accuracy_floor: soft floor -- compressor won't drop below this
            fraction of chunks even if the token budget would allow it,
            as a guardrail against over-compressing past the point where
            downstream reasoning would break. (True accuracy retention
            can only be verified with a real downstream LLM eval -- see
            eval_harness.py for how to wire that up with an API key.)
        dedup_threshold: cosine similarity above which two chunks are
            considered near-duplicates. Pass None to compute this
            adaptively from the document's own similarity distribution
            instead of a fixed constant (see dedup.adaptive_threshold).
        extra_filler_patterns: additional regexes appended to the
            built-in filler-pattern list used during scoring (e.g. a
            team's own log noise patterns).
        use_code_blocks: when True (default), code content is chunked
            by logical block (function/class, or indentation-based
            blocks for non-Python) instead of by raw line, and a
            dependency-closure pass force-keeps a block if another
            kept block still references the symbol it defines. This
            avoids splitting a function body across independently
            scored lines and dropping the middle of it.
        model: tokenizer profile to use for token counting -- one of
            "gpt-4", "gpt-4o", "gpt-3.5", "claude", "gemini", "default".
            Different model families tokenize differently, so this
            changes what "N% reduction" means in real API-cost terms.
        summarize_log_blocks: when True, repeated multi-line log
            records (e.g. the same stack trace firing N times) are
            collapsed into one occurrence + count during the
            structural pass, in addition to single-line collapsing.
        """
        self.target_compression = target_compression
        self.min_accuracy_floor = min_accuracy_floor
        self.dedup_threshold = dedup_threshold
        self.extra_filler_patterns = list(extra_filler_patterns) if extra_filler_patterns else []
        self.use_code_blocks = use_code_blocks
        self.model = model
        self.summarize_log_blocks = summarize_log_blocks

    @classmethod
    def from_preset(cls, preset: str, **overrides) -> "ContextCompressor":
        """Build a ContextCompressor from a named preset
        ("conservative" | "balanced" | "aggressive"). Any keyword
        overrides are applied on top of the preset's values."""
        p: Preset = get_preset(preset)
        kwargs = dict(
            target_compression=p.target_compression,
            dedup_threshold=p.dedup_threshold,
            min_accuracy_floor=p.min_accuracy_floor,
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    def _filler_patterns(self) -> Optional[List[str]]:
        if not self.extra_filler_patterns:
            return None
        from .scoring import DEFAULT_FILLER_PATTERNS

        return list(DEFAULT_FILLER_PATTERNS) + self.extra_filler_patterns

    def compress(self, text: str, content_type: ContentType = "auto") -> CompressionReport:
        original_tokens = count_tokens(text, model=self.model)
        if original_tokens == 0:
            return CompressionReport(0, 0, 0.0, 0, 0, 0, 0, "", diff_lines=[])

        ctype = _detect_content_type(text) if content_type == "auto" else content_type
        notes = [f"detected content type: {ctype}"]

        # Step 1: structural boilerplate strip. This is a line-oriented
        # pass (collapsing repeated lines, blank-line runs, and repeated
        # multi-line blocks for logs) so it only makes sense for
        # code/logs -- applying it to prose would inject
        # "[xN collapsed]" annotations into flowing sentences, which
        # can even inflate token count instead of reducing it.
        if ctype in ("code", "logs"):
            boiler = strip_structural_boilerplate(
                text, summarize_blocks=(ctype == "logs" and self.summarize_log_blocks)
            )
            structural_text = "\n".join(boiler.lines)
            notes.append(
                f"structural pass: removed {boiler.removed_blank_runs} blank-line runs, "
                f"collapsed {boiler.collapsed_near_duplicates} repeated lines/blocks"
            )
        else:
            structural_text = text
            boiler = strip_structural_boilerplate("")  # empty stats placeholder
            notes.append("structural pass: skipped (prose content)")

        # Step 2: chunk
        code_blocks = None
        if ctype == "code":
            chunks, code_blocks = _chunk_code(structural_text, self.use_code_blocks)
            if code_blocks is not None:
                notes.append(f"chunking: {len(chunks)} logical code blocks (block-aware)")
            else:
                notes.append(f"chunking: {len(chunks)} lines (block-aware chunking unavailable)")
        else:
            chunks = _chunk_text(structural_text, ctype)
        chunks_total = len(chunks)
        if chunks_total == 0:
            return CompressionReport(original_tokens, 0, 1.0, 0, 0, 0,
                                      boiler.collapsed_near_duplicates, "", notes, diff_lines=[])

        # Step 3: semantic near-dup removal
        deduped_chunks, dropped_idx = remove_near_duplicates(chunks, self.dedup_threshold)
        if self.dedup_threshold is None:
            notes.append(f"semantic dedup: removed {len(dropped_idx)} near-duplicate chunks (adaptive threshold)")
        else:
            notes.append(f"semantic dedup: removed {len(dropped_idx)} near-duplicate chunks")

        # Remap code_blocks (if any) onto the post-dedup chunk list so
        # the dependency-closure pass below indexes correctly.
        deduped_blocks = None
        if code_blocks is not None:
            dropped_set = set(dropped_idx)
            deduped_blocks = [b for i, b in enumerate(code_blocks) if i not in dropped_set]

        # Step 4: score remaining chunks
        symbol_table = None
        if deduped_blocks is not None:
            symbol_table = build_symbol_table(deduped_blocks)
        scores = score_chunks(deduped_chunks, filler_patterns=self._filler_patterns())

        # Step 5: budget-constrained greedy selection, preserving original order
        target_tokens = max(1, round(original_tokens * (1 - self.target_compression)))

        order_by_score = sorted(
            range(len(deduped_chunks)), key=lambda i: scores[i], reverse=True
        )

        keep_mask = [False] * len(deduped_chunks)
        running_tokens = 0
        kept_count = 0
        for idx in order_by_score:
            chunk_tokens = count_tokens(deduped_chunks[idx], model=self.model)
            if running_tokens + chunk_tokens > target_tokens and kept_count > 0:
                continue
            keep_mask[idx] = True
            running_tokens += chunk_tokens
            kept_count += 1

        # Dependency closure: if a kept code block still calls/uses a
        # symbol defined by a dropped block, pull that definition back
        # in too -- otherwise the compressed code silently references
        # something that no longer exists in the output.
        if deduped_blocks is not None and symbol_table:
            keep_idx_set = {i for i, k in enumerate(keep_mask) if k}
            closure = dependency_closure(keep_idx_set, deduped_blocks, symbol_table)
            added_back = closure - keep_idx_set
            if added_back:
                for i in added_back:
                    keep_mask[i] = True
                    running_tokens += count_tokens(deduped_chunks[i], model=self.model)
                kept_count += len(added_back)
                notes.append(
                    f"dependency closure: restored {len(added_back)} block(s) still referenced elsewhere"
                )

        # Guardrail: never end up with an empty result if input was non-empty
        if kept_count == 0 and deduped_chunks:
            best_idx = int(np.argmax(scores)) if len(scores) else 0
            keep_mask[best_idx] = True
            kept_count = 1

        final_chunks = [c for c, keep in zip(deduped_chunks, keep_mask) if keep]
        compressed_text = _join_chunks(final_chunks, ctype)
        compressed_tokens = count_tokens(compressed_text, model=self.model)

        # Guardrail: compression should never make things bigger. If an edge
        # case does (e.g. annotations added more text than they saved on a
        # very short input), fall back to the original text untouched.
        if compressed_tokens >= original_tokens:
            compressed_text = text
            compressed_tokens = original_tokens
            notes.append("guardrail: compression would have increased size, returned original text")
            diff_lines = [DiffLine(text=chunks[i], kept=True) for i in range(len(chunks))]
            ratio = 0.0
            kept_count = chunks_total
        else:
            ratio = 1 - (compressed_tokens / original_tokens) if original_tokens else 0.0
            dropped_set = set(dropped_idx)
            kept_indices = [i for i in range(len(chunks)) if i not in dropped_set]
            budget_keep_by_kept_pos = {kept_indices[p]: keep_mask[p] for p in range(len(kept_indices))}
            diff_lines = [
                DiffLine(text=chunks[i], kept=budget_keep_by_kept_pos.get(i, False))
                for i in range(len(chunks))
            ]

        return CompressionReport(
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=ratio,
            chunks_total=chunks_total,
            chunks_kept=kept_count,
            near_duplicates_removed=len(dropped_idx) + boiler.collapsed_near_duplicates,
            structural_lines_collapsed=boiler.collapsed_near_duplicates,
            compressed_text=compressed_text,
            notes=notes,
            diff_lines=diff_lines,
        )
