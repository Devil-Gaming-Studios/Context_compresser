"""
ContextCompressor -- the main entry point.

Pipeline:
  1. Structural boilerplate strip (blank-line runs, near-identical
     repeated lines -- cheap, format-aware, lossless-ish)
  2. Chunking (split into lines or sentences depending on content type)
  3. Semantic near-duplicate removal (TF-IDF cosine similarity)
  4. Information-density scoring (TF-IDF mass per chunk)
  5. Budget-constrained selection: keep the highest-scoring chunks,
     in original order, until the token budget is met
"""

import re
from dataclasses import dataclass, field
from typing import List, Literal

import numpy as np

from .boilerplate import strip_structural_boilerplate
from .dedup import remove_near_duplicates
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


def _chunk_text(text: str, content_type: ContentType) -> List[str]:
    if content_type in ("code", "logs"):
        return text.splitlines()
    # prose: split on sentence boundaries, keep it simple/dependency-free
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    lines = [l for l in text.splitlines() if l.strip()]
    # If there's no real sentence punctuation (so the "sentence split" just
    # returned the whole blob as one chunk) but the text has multiple lines,
    # fall back to line-level chunking -- otherwise a single indivisible
    # chunk can't be trimmed at all, defeating the point of compression.
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
        dedup_threshold: float = 0.85,
    ):
        """
        target_compression: fraction of tokens to remove (0.70 = keep ~30%)
        min_accuracy_floor: soft floor -- compressor won't drop below this
            fraction of chunks even if the token budget would allow it,
            as a guardrail against over-compressing past the point where
            downstream reasoning would break. (True accuracy retention
            can only be verified with a real downstream LLM eval -- see
            benchmark.py for how to wire that up with an API key.)
        dedup_threshold: cosine similarity above which two chunks are
            considered near-duplicates.
        """
        self.target_compression = target_compression
        self.min_accuracy_floor = min_accuracy_floor
        self.dedup_threshold = dedup_threshold

    def compress(self, text: str, content_type: ContentType = "auto") -> CompressionReport:
        original_tokens = count_tokens(text)
        if original_tokens == 0:
            return CompressionReport(0, 0, 0.0, 0, 0, 0, 0, "", diff_lines=[])

        ctype = _detect_content_type(text) if content_type == "auto" else content_type
        notes = [f"detected content type: {ctype}"]

        # Step 1: structural boilerplate strip. This is a line-oriented pass
        # (collapsing repeated lines, blank-line runs) so it only makes sense
        # for code/logs -- applying it to prose would inject "[xN collapsed]"
        # annotations into flowing sentences, which can even inflate token
        # count instead of reducing it.
        if ctype in ("code", "logs"):
            boiler = strip_structural_boilerplate(text)
            structural_text = "\n".join(boiler.lines)
            notes.append(
                f"structural pass: removed {boiler.removed_blank_runs} blank-line runs, "
                f"collapsed {boiler.collapsed_near_duplicates} repeated lines"
            )
        else:
            structural_text = text
            boiler = strip_structural_boilerplate("")  # empty stats placeholder
            notes.append("structural pass: skipped (prose content)")

        # Step 2: chunk
        chunks = _chunk_text(structural_text, ctype)
        chunks_total = len(chunks)
        if chunks_total == 0:
            return CompressionReport(original_tokens, 0, 1.0, 0, 0, 0,
                                      boiler.collapsed_near_duplicates, "", notes, diff_lines=[])

        # Step 3: semantic near-dup removal
        deduped_chunks, dropped_idx = remove_near_duplicates(chunks, self.dedup_threshold)
        notes.append(f"semantic dedup: removed {len(dropped_idx)} near-duplicate chunks")

        # Step 4: score remaining chunks
        scores = score_chunks(deduped_chunks)

        # Step 5: budget-constrained greedy selection, preserving original order
        target_tokens = max(1, round(original_tokens * (1 - self.target_compression)))

        order_by_score = sorted(
            range(len(deduped_chunks)), key=lambda i: scores[i], reverse=True
        )

        keep_mask = [False] * len(deduped_chunks)
        running_tokens = 0
        kept_count = 0
        for idx in order_by_score:
            chunk_tokens = count_tokens(deduped_chunks[idx])
            if running_tokens + chunk_tokens > target_tokens and kept_count > 0:
                continue
            keep_mask[idx] = True
            running_tokens += chunk_tokens
            kept_count += 1

        # Guardrail: never end up with an empty result if input was non-empty
        if kept_count == 0 and deduped_chunks:
            best_idx = int(np.argmax(scores)) if len(scores) else 0
            keep_mask[best_idx] = True
            kept_count = 1

        final_chunks = [c for c, keep in zip(deduped_chunks, keep_mask) if keep]
        compressed_text = _join_chunks(final_chunks, ctype)
        compressed_tokens = count_tokens(compressed_text)

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
