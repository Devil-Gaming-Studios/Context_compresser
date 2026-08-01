"""
Code-aware chunking and symbol analysis.

Line-level chunking (the original approach) can split a function body
across several independently-scored chunks -- one line of a function
might score high and survive while a sibling line is dropped, leaving
behind syntactically-broken or semantically-misleading fragments.

This module offers two upgrades on top of plain line-splitting:

1. Block chunking -- group code into logical units (functions, classes,
   top-level statements) so scoring/selection operates on whole blocks
   instead of individual lines. Python uses the `ast` module for exact
   boundaries; other languages fall back to an indentation-based
   heuristic (a new block starts when indentation returns to a
   shallower level after being deeper).

2. Symbol table -- a lightweight map of "name -> defining block index"
   and "block index -> names it references". This lets the compressor
   force-keep a definition if something else being kept still calls it,
   even when the definition's own TF-IDF score is low (e.g. a short
   one-line helper function with no comments).

Both are best-effort heuristics, not a real parser/linter -- they're
meant to reduce the odds of the compressor producing code that looks
plausible but silently drops a dependency, not to guarantee correctness.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class CodeBlock:
    text: str
    start_line: int
    end_line: int
    defines: Set[str] = field(default_factory=set)
    references: Set[str] = field(default_factory=set)


_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

# Words that show up constantly as "references" but aren't meaningful
# call/usage signals -- skip them so the dependency graph doesn't get
# swamped with noise.
_PY_KEYWORDS = {
    "def", "class", "return", "if", "elif", "else", "for", "while", "try",
    "except", "finally", "with", "as", "import", "from", "pass", "break",
    "continue", "raise", "yield", "lambda", "global", "nonlocal", "assert",
    "del", "in", "is", "not", "and", "or", "None", "True", "False", "self",
    "cls", "async", "await",
}


def _references_in(text: str) -> Set[str]:
    return {t for t in _IDENT_RE.findall(text) if t not in _PY_KEYWORDS}


def chunk_python_by_block(text: str) -> List[CodeBlock]:
    """
    Split Python source into top-level logical blocks (function defs,
    class defs, and runs of other top-level statements) using `ast`.
    Falls back to `None` if the source doesn't parse -- caller should
    fall back to indentation-based or line-based chunking in that case.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    lines = text.splitlines()
    blocks: List[CodeBlock] = []
    covered_to = 0  # 1-indexed line number already emitted up to

    def flush_gap(up_to_line: int):
        """Emit any top-level lines between the last block and up_to_line
        (imports, module docstring, loose statements, comments) as their
        own block so nothing gets silently dropped from chunking."""
        nonlocal covered_to
        if up_to_line > covered_to:
            gap_lines = lines[covered_to:up_to_line]
            gap_text = "\n".join(gap_lines)
            if gap_text.strip():
                blocks.append(
                    CodeBlock(
                        text=gap_text,
                        start_line=covered_to + 1,
                        end_line=up_to_line,
                        defines=set(),
                        references=_references_in(gap_text),
                    )
                )
        covered_to = up_to_line

    for node in tree.body:
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        flush_gap(start - 1)

        block_text = "\n".join(lines[start - 1:end])
        defines = set()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defines.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defines.add(t.id)

        blocks.append(
            CodeBlock(
                text=block_text,
                start_line=start,
                end_line=end,
                defines=defines,
                references=_references_in(block_text) - defines,
            )
        )
        covered_to = end

    flush_gap(len(lines))
    return blocks


def chunk_code_by_indentation(text: str) -> List[CodeBlock]:
    """
    Language-agnostic fallback: group lines into blocks by indentation --
    a new block starts whenever a line's indentation drops back to a
    shallower (or equal top-level) depth after the previous block went
    deeper. This is a heuristic, not a real parser, but it keeps
    braces/indented bodies together for non-Python languages (JS, Go,
    Java, C-family, etc.) far better than splitting every line alone.
    """
    lines = text.splitlines()
    if not lines:
        return []

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" \t")) if line.strip() else -1

    blocks: List[CodeBlock] = []
    current: List[str] = []
    current_start = 1
    base_indent = None

    def flush(end_line: int):
        nonlocal current, current_start
        if current:
            block_text = "\n".join(current)
            blocks.append(
                CodeBlock(
                    text=block_text,
                    start_line=current_start,
                    end_line=end_line,
                    defines=set(),
                    references=_references_in(block_text),
                )
            )
        current = []

    went_deeper = False
    for i, line in enumerate(lines, start=1):
        ind = indent_of(line)
        if not current:
            current = [line]
            current_start = i
            base_indent = ind if ind >= 0 else None
            went_deeper = False
            continue
        if base_indent is None and ind >= 0:
            base_indent = ind
        if ind >= 0 and base_indent is not None:
            if ind > base_indent:
                went_deeper = True
            elif ind <= base_indent and went_deeper:
                flush(i - 1)
                current = [line]
                current_start = i
                base_indent = ind
                went_deeper = False
                continue
        current.append(line)
    flush(len(lines))
    return blocks


def build_symbol_table(blocks: List[CodeBlock]) -> Dict[str, int]:
    """Map defined-symbol-name -> index of the block that defines it.
    If multiple blocks define the same name, the last definition wins
    (mirrors normal shadowing/redefinition semantics)."""
    table: Dict[str, int] = {}
    for i, b in enumerate(blocks):
        for name in b.defines:
            table[name] = i
    return table


def dependency_closure(keep_indices: Set[int], blocks: List[CodeBlock], symbol_table: Dict[str, int]) -> Set[int]:
    """
    Given a set of block indices already selected to keep, expand it to
    include any block that defines a symbol referenced by a kept block
    (transitively) -- so keeping a call site also keeps its definition.
    """
    result = set(keep_indices)
    frontier = list(keep_indices)
    while frontier:
        idx = frontier.pop()
        for ref in blocks[idx].references:
            def_idx = symbol_table.get(ref)
            if def_idx is not None and def_idx not in result:
                result.add(def_idx)
                frontier.append(def_idx)
    return result
