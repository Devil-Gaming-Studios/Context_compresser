"""
Diff-aware compression.

Everything else in this package compresses a *snapshot*: a file, or a
directory of files, treated as a flat bag of content. That's the wrong
unit of work for the most common real usage pattern -- "here's a PR /
commit, give the model enough context to review or reason about just
the change" -- because it has no idea which lines are the actual edit
and which are unrelated surrounding code.

This module adds that: parse a unified diff, find which logical code
blocks (from code_chunker) the diff actually touches, and compress
each changed file so that:

  1. Every block touched by the diff is force-kept (never dropped --
     the whole point is to preserve the edit itself).
  2. Any symbol a touched block depends on (via the existing
     dependency-closure pass) is pulled in too, even if it wasn't
     itself changed -- otherwise the model sees a call to something
     that doesn't exist in the compressed output.
  3. Everything else in the file (unchanged, unreferenced code) is
     compressed/dropped normally against the token budget.

Input can be a raw unified diff (e.g. `git diff`, or a `.diff` fetched
from a GitHub PR/compare URL) plus the *new* full text of each changed
file, or a local git repo + refs (in which case this module shells out
to `git` itself). No network access or GitHub API calls are involved
either way -- if you want to diff a GitHub PR, fetch its `.diff` URL
or `git clone` it yourself and pass the result in.
"""

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .code_chunker import (
    CodeBlock,
    build_symbol_table,
    chunk_code_by_indentation,
    chunk_python_by_block,
)
from .compressor import DiffLine
from .scoring import score_chunks
from .tokenizer import count_tokens

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")
_OLD_FILE_HEADER_RE = re.compile(r"^--- a/(.+)$")


@dataclass
class DiffHunk:
    new_start: int
    new_lines: int  # count of lines in the hunk on the "new" side (context + added)

    @property
    def new_end(self) -> int:
        return self.new_start + max(self.new_lines - 1, 0)


@dataclass
class DiffBlockReport:
    path: str
    original_tokens: int
    compressed_tokens: int
    compressed_text: str
    changed_blocks_kept: int
    context_blocks_kept: int
    dependency_blocks_restored: int
    blocks_total: int
    diff_lines: List[DiffLine] = field(default_factory=list)


@dataclass
class DiffCompressionReport:
    files: List[DiffBlockReport]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    files_skipped: List[str] = field(default_factory=list)  # e.g. deleted/binary/non-code
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.files)} changed file(s), {self.original_tokens} -> "
            f"{self.compressed_tokens} tokens ({self.compression_ratio * 100:.1f}% reduction)"
        )


def parse_unified_diff(diff_text: str) -> Dict[str, List[DiffHunk]]:
    """
    Parse a unified diff (as produced by `git diff`, `git show`, or a
    GitHub PR's `.diff` endpoint) into {new_file_path: [DiffHunk, ...]}.

    Only the "new file" side is tracked, since that's what we chunk and
    compress -- we don't need old-side line numbers for anything here.
    Deleted files (no `+++ b/...` target, i.e. `/dev/null`) are skipped;
    there's no new content to compress.
    """
    files: Dict[str, List[DiffHunk]] = {}
    current_path: Optional[str] = None

    for line in diff_text.splitlines():
        m_new = _FILE_HEADER_RE.match(line)
        if m_new:
            path = m_new.group(1).strip()
            current_path = None if path == "/dev/null" else path
            if current_path is not None:
                files.setdefault(current_path, [])
            continue

        if current_path is None:
            continue

        m_hunk = _HUNK_HEADER_RE.match(line)
        if m_hunk:
            new_start = int(m_hunk.group(1))
            new_lines = int(m_hunk.group(2)) if m_hunk.group(2) is not None else 1
            files[current_path].append(DiffHunk(new_start=new_start, new_lines=new_lines))

    # Drop entries with zero hunks (e.g. pure renames with no content change)
    return {p: h for p, h in files.items() if h}


def get_repo_diff(repo_path: str, base_ref: str = "HEAD", target_ref: Optional[str] = None) -> str:
    """
    Shell out to `git diff` inside a local repo. If target_ref is None,
    diffs base_ref against the working tree (i.e. "what's changed but
    maybe not committed yet"); otherwise diffs base_ref..target_ref.

    Requires `git` to be installed and repo_path to be inside a git
    working copy. Raises RuntimeError on failure (not a repo, bad ref,
    git not found, etc.) so callers get a clear error instead of a
    silently empty diff.
    """
    args = ["git", "-C", repo_path, "diff", "--no-color"]
    args.append(f"{base_ref}..{target_ref}" if target_ref else base_ref)
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError("git is not installed or not on PATH")
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def get_file_at_ref(repo_path: str, ref: str, path: str) -> str:
    """Read a file's content as of a given git ref (empty string ref
    means the working tree, i.e. just read it off disk)."""
    if not ref or ref == "WORKTREE":
        import os

        with open(os.path.join(repo_path, path), "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    result = subprocess.run(
        ["git", "-C", repo_path, "show", f"{ref}:{path}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show failed for {path}@{ref}: {result.stderr.strip()}")
    return result.stdout


def _chunk_file(path: str, text: str) -> List[CodeBlock]:
    blocks = chunk_python_by_block(text) if path.endswith(".py") else None
    if blocks is None:
        blocks = chunk_code_by_indentation(text)
    return blocks or []


def _touched_block_indices(blocks: List[CodeBlock], hunks: List[DiffHunk]) -> set:
    touched = set()
    for i, b in enumerate(blocks):
        for h in hunks:
            # overlap test between [b.start_line, b.end_line] and [h.new_start, h.new_end]
            if b.start_line <= h.new_end and h.new_start <= b.end_line:
                touched.add(i)
                break
    return touched


def _select_blocks_for_file(blocks, hunks, original_tokens, target_compression, model):
    """First pass, single file: force-keep touched blocks, fill the
    remaining budget with the highest-value context. Cross-file
    dependency closure happens separately in compress_diff, since a
    single file doesn't know what other changed files need from it."""
    changed_idx = _touched_block_indices(blocks, hunks)
    target_tokens = max(1, round(original_tokens * (1 - target_compression)))

    keep_mask = [False] * len(blocks)
    running_tokens = 0
    for i in changed_idx:
        keep_mask[i] = True
        running_tokens += count_tokens(blocks[i].text, model=model)

    context_idx = [i for i in range(len(blocks)) if i not in changed_idx]
    if context_idx:
        context_texts = [blocks[i].text for i in context_idx]
        context_scores = score_chunks(context_texts)
        order = sorted(range(len(context_idx)), key=lambda k: context_scores[k], reverse=True)
        for k in order:
            i = context_idx[k]
            t = count_tokens(blocks[i].text, model=model)
            if running_tokens + t > target_tokens:
                continue
            keep_mask[i] = True
            running_tokens += t

    return keep_mask, changed_idx


def _finalize_file(path, new_text, blocks, keep_mask, changed_idx, dependency_restored, model):
    original_tokens = count_tokens(new_text, model=model)
    keep_idx_set = {i for i, k in enumerate(keep_mask) if k}
    final_blocks = [b.text for b, k in zip(blocks, keep_mask) if k]
    compressed_text = "\n\n".join(final_blocks)
    compressed_tokens = count_tokens(compressed_text, model=model)

    if compressed_tokens >= original_tokens:
        compressed_text = new_text
        compressed_tokens = original_tokens
        keep_mask = [True] * len(blocks)
        keep_idx_set = set(range(len(blocks)))

    diff_lines = [DiffLine(text=b.text, kept=keep_mask[i]) for i, b in enumerate(blocks)]

    return DiffBlockReport(
        path=path,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        compressed_text=compressed_text,
        changed_blocks_kept=len(changed_idx),
        context_blocks_kept=len(keep_idx_set - changed_idx) - dependency_restored,
        dependency_blocks_restored=dependency_restored,
        blocks_total=len(blocks),
        diff_lines=diff_lines,
    )


def compress_diff(
    *,
    repo_path: Optional[str] = None,
    base_ref: str = "HEAD",
    target_ref: Optional[str] = None,
    diff_text: Optional[str] = None,
    file_contents: Optional[Dict[str, str]] = None,
    target_compression: float = 0.70,
    model: str = "default",
) -> DiffCompressionReport:
    """
    Compress only what a diff touches, plus whatever context (symbol
    dependencies + highest-value surrounding code) fits the budget.

    Two ways to call this:

    1. Local repo:      compress_diff(repo_path="./myrepo", base_ref="HEAD~1")
       -- shells out to `git diff` and `git show` itself.

    2. Bring your own diff (e.g. downloaded from a GitHub PR's `.diff`
       URL, or a diff produced elsewhere with no git repo on disk):
           compress_diff(diff_text=raw_diff_text, file_contents={"a/b.py": "...full new source..."})
       -- file_contents keys must match the paths in the diff's `+++ b/...` headers.

    Either `repo_path` or (`diff_text` + `file_contents`) must be given.
    """
    if diff_text is None:
        if repo_path is None:
            raise ValueError("compress_diff requires either repo_path or diff_text")
        diff_text = get_repo_diff(repo_path, base_ref=base_ref, target_ref=target_ref)

    hunks_by_file = parse_unified_diff(diff_text)
    notes = [f"parsed diff: {len(hunks_by_file)} changed file(s)"]

    skipped: List[str] = []
    file_texts: Dict[str, str] = {}
    for path in hunks_by_file:
        try:
            if file_contents is not None:
                text = file_contents.get(path) or file_contents.get(f"b/{path}")
                if text is None:
                    skipped.append(path)
                    continue
            else:
                text = get_file_at_ref(repo_path, target_ref or "WORKTREE", path)
        except (RuntimeError, OSError):
            skipped.append(path)
            continue
        file_texts[path] = text

    file_blocks: Dict[str, List[CodeBlock]] = {}
    keep_masks: Dict[str, List[bool]] = {}
    changed_idx_by_file: Dict[str, set] = {}
    for path, text in file_texts.items():
        blocks = _chunk_file(path, text)
        original_tokens = count_tokens(text, model=model)
        if not blocks:
            file_blocks[path] = []
            keep_masks[path] = []
            changed_idx_by_file[path] = set()
            continue
        keep_mask, changed_idx = _select_blocks_for_file(
            blocks, hunks_by_file[path], original_tokens, target_compression, model
        )
        file_blocks[path] = blocks
        keep_masks[path] = keep_mask
        changed_idx_by_file[path] = changed_idx

    global_symbol_table: Dict[str, Tuple[str, int]] = {}
    for path, blocks in file_blocks.items():
        for name, idx in build_symbol_table(blocks).items():
            global_symbol_table[name] = (path, idx)

    restored_by_file: Dict[str, int] = {p: 0 for p in file_blocks}
    changed = True
    while changed:
        changed = False
        for path, blocks in file_blocks.items():
            mask = keep_masks[path]
            for i, b in enumerate(blocks):
                if not mask[i]:
                    continue
                for ref in b.references:
                    loc = global_symbol_table.get(ref)
                    if loc is None:
                        continue
                    ref_path, ref_idx = loc
                    if ref_path == path and ref_idx == i:
                        continue
                    if not keep_masks[ref_path][ref_idx]:
                        keep_masks[ref_path][ref_idx] = True
                        restored_by_file[ref_path] += 1
                        changed = True

    files: List[DiffBlockReport] = []
    total_original = 0
    total_compressed = 0
    for path, text in file_texts.items():
        blocks = file_blocks[path]
        if not blocks:
            tok = count_tokens(text, model=model)
            report = DiffBlockReport(
                path=path, original_tokens=tok, compressed_tokens=tok, compressed_text=text,
                changed_blocks_kept=0, context_blocks_kept=0, dependency_blocks_restored=0,
                blocks_total=0, diff_lines=[DiffLine(text=text, kept=True)],
            )
        else:
            report = _finalize_file(
                path, text, blocks, keep_masks[path], changed_idx_by_file[path],
                restored_by_file[path], model,
            )
        files.append(report)
        total_original += report.original_tokens
        total_compressed += report.compressed_tokens

    total_restored = sum(restored_by_file.values())
    if total_restored:
        notes.append(f"cross-file dependency closure restored {total_restored} block(s)")
    if skipped:
        notes.append(f"skipped {len(skipped)} file(s) with unavailable content: {', '.join(skipped)}")

    ratio = 1 - (total_compressed / total_original) if total_original else 0.0

    return DiffCompressionReport(
        files=files,
        original_tokens=total_original,
        compressed_tokens=total_compressed,
        compression_ratio=ratio,
        files_skipped=skipped,
        notes=notes,
    )
