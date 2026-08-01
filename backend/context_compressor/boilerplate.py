"""
Structural boilerplate stripping.

These are format-aware heuristics applied BEFORE semantic scoring:
- collapse runs of blank lines
- dedupe exact-repeat lines (common in logs: identical heartbeat/status
  lines repeated hundreds of times)
- collapse near-identical log lines that differ only in a timestamp or
  a numeric field (e.g. "req_id=1823" vs "req_id=1824") into one
  representative line + a count
- strip common low-information code boilerplate (license headers,
  auto-generated markers) when explicitly enabled
"""

import re
from dataclasses import dataclass, field
from typing import List


_TS_OR_NUM = re.compile(r"\b\d[\d:,.\-T]*\d\b|\b\d+\b")


def _normalize_for_dedup(line: str) -> str:
    """Collapse timestamps/ids/numbers so near-duplicate log lines match."""
    return _TS_OR_NUM.sub("<N>", line.strip())


@dataclass
class BoilerplateResult:
    lines: List[str]
    removed_exact_duplicates: int = 0
    removed_blank_runs: int = 0
    collapsed_near_duplicates: int = 0
    collapse_notes: List[str] = field(default_factory=list)


def strip_structural_boilerplate(text: str) -> BoilerplateResult:
    raw_lines = text.splitlines()

    # 1. Collapse runs of blank lines to a single blank line.
    collapsed_blanks = []
    blank_run = 0
    removed_blank_runs = 0
    for line in raw_lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                collapsed_blanks.append(line)
            else:
                removed_blank_runs += 1
        else:
            blank_run = 0
            collapsed_blanks.append(line)

    # 2. Collapse near-duplicate lines (same after normalizing numbers),
    #    keeping the first occurrence and a "(xN)" count marker.
    seen_normalized = {}
    order = []
    for line in collapsed_blanks:
        if line.strip() == "":
            order.append(line)
            continue
        key = _normalize_for_dedup(line)
        if key in seen_normalized:
            seen_normalized[key] += 1
        else:
            seen_normalized[key] = 1
            order.append(line)

    final_lines = []
    collapsed_near_duplicates = 0
    notes = []
    normalized_cache = {}
    for line in order:
        if line.strip() == "":
            final_lines.append(line)
            continue
        key = _normalize_for_dedup(line)
        count = seen_normalized[key]
        if count > 1:
            final_lines.append(f"{line}  [x{count} similar lines collapsed]")
            collapsed_near_duplicates += count - 1
            notes.append(f"{count}x: {line.strip()[:60]}")
        else:
            final_lines.append(line)

    return BoilerplateResult(
        lines=final_lines,
        removed_exact_duplicates=0,  # folded into near-duplicate collapse
        removed_blank_runs=removed_blank_runs,
        collapsed_near_duplicates=collapsed_near_duplicates,
        collapse_notes=notes[:10],
    )
