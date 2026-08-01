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
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?|\d{2}:\d{2}:\d{2}")
_RECORD_START = re.compile(r"^\s*(\[?\d{4}-\d{2}-\d{2}|(INFO|DEBUG|WARN|WARNING|ERROR|CRITICAL|Traceback)\b)")


def _normalize_for_dedup(line: str) -> str:
    """Collapse timestamps/ids/numbers so near-duplicate log lines match."""
    return _TS_OR_NUM.sub("<N>", line.strip())


def _split_into_records(lines: List[str]) -> List[List[str]]:
    """
    Group log lines into multi-line "records" -- e.g. a stack trace or a
    multi-line error dump belongs with the log line that introduced it,
    not treated as independent unrelated lines. A new record starts at
    a line matching a timestamp/log-level/Traceback marker, or at a
    blank line; everything until the next marker is folded in.
    """
    records: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                records.append(current)
                current = []
            records.append([line])
            continue
        if _RECORD_START.match(line) and current:
            records.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        records.append(current)
    return records


def _normalize_record(record: List[str]) -> str:
    return "\n".join(_normalize_for_dedup(l) for l in record)


@dataclass
class RepeatedBlockResult:
    lines: List[str]
    blocks_collapsed: int = 0
    notes: List[str] = field(default_factory=list)


def summarize_repeated_blocks(text: str, min_block_lines: int = 2, min_repeats: int = 3) -> RepeatedBlockResult:
    """
    Collapse consecutive repeated multi-line records (e.g. the same
    stack trace or multi-line error firing repeatedly) into a single
    representative occurrence plus a count and, if timestamps are
    present, the first/last occurrence times. This is a step up from
    single-line dedup (in `strip_structural_boilerplate`) which can't
    see that a 6-line traceback repeated 40 times is a single event
    class, not 240 unrelated lines.

    Only consecutive runs are collapsed (a repeated block that recurs
    with other content interleaved is left alone -- collapsing those
    would risk erasing genuinely-different intervening events).
    """
    lines = text.splitlines()
    records = _split_into_records(lines)

    out_records: List[List[str]] = []
    notes = []
    blocks_collapsed = 0
    i = 0
    while i < len(records):
        rec = records[i]
        if len(rec) < min_block_lines or not any(l.strip() for l in rec):
            out_records.append(rec)
            i += 1
            continue

        key = _normalize_record(rec)
        run = [rec]
        j = i + 1
        while j < len(records) and _normalize_record(records[j]) == key:
            run.append(records[j])
            j += 1

        if len(run) >= min_repeats:
            first_ts = None
            last_ts = None
            m = _TIMESTAMP.search(rec[0])
            if m:
                first_ts = m.group(0)
                m2 = _TIMESTAMP.search(run[-1][0])
                last_ts = m2.group(0) if m2 else None
            suffix = f"  [repeated block x{len(run)}"
            if first_ts:
                suffix += f", {first_ts} .. {last_ts or first_ts}"
            suffix += "]"
            collapsed = list(rec)
            collapsed[-1] = collapsed[-1] + suffix
            out_records.append(collapsed)
            blocks_collapsed += len(run) - 1
            notes.append(f"{len(run)}x block starting: {rec[0].strip()[:60]}")
            i = j
        else:
            out_records.append(rec)
            i += 1

    flat = [l for rec in out_records for l in rec]
    return RepeatedBlockResult(lines=flat, blocks_collapsed=blocks_collapsed, notes=notes[:10])


@dataclass
class BoilerplateResult:
    lines: List[str]
    removed_exact_duplicates: int = 0
    removed_blank_runs: int = 0
    collapsed_near_duplicates: int = 0
    collapse_notes: List[str] = field(default_factory=list)


def strip_structural_boilerplate(text: str, summarize_blocks: bool = False) -> BoilerplateResult:
    block_notes = []
    blocks_collapsed = 0
    if summarize_blocks and text.strip():
        block_result = summarize_repeated_blocks(text)
        text = "\n".join(block_result.lines)
        block_notes = block_result.notes
        blocks_collapsed = block_result.blocks_collapsed

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
        collapsed_near_duplicates=collapsed_near_duplicates + blocks_collapsed,
        collapse_notes=(block_notes + notes)[:10],
    )
