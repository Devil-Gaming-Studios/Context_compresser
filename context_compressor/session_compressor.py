"""
Session compression -- compress chat/conversation exports (ChatGPT,
Claude, or a generic {role, content} transcript) for reuse as context
(e.g. re-feeding history into a fresh session, or trimming a long
Claude Code / agent conversation before it blows the context window).

Strategy ("hermes"-style):
  - The system prompt (if any) is always kept verbatim -- it's usually
    small and load-bearing.
  - The most recent `protect_recent` turns are always kept verbatim --
    recent context is disproportionately relevant to what happens next,
    and truncating it tends to break follow-up references ("that file",
    "the error above").
  - Every older turn is run through the normal ContextCompressor
    (content-type "prose" by default, since chat turns are rarely pure
    code/log dumps) to strip filler and near-duplicate phrasing.
  - Near-duplicate *whole turns* among the older turns (e.g. the user
    repeating a question after a bad answer, or the assistant repeating
    a boilerplate caveat) are dropped entirely, keeping the first
    occurrence.

A "turn" here means one message. Multi-message exchanges are just
consecutive messages; we don't try to merge them.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from .compressor import ContextCompressor
from .dedup import remove_near_duplicates
from .tokenizer import count_tokens

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Turn:
    role: Role
    content: str
    # Best-effort passthrough of any extra fields the source format had
    # (timestamps, message ids, etc.) so a round-tripped export doesn't
    # lose metadata other tooling might rely on.
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnReport:
    role: Role
    original_tokens: int
    compressed_tokens: int
    action: Literal["protected_system", "protected_recent", "compressed", "dropped_duplicate"]
    content: str  # the surviving (possibly compressed) content; empty if dropped


@dataclass
class SessionCompressionReport:
    turns: List[TurnReport]
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    turns_total: int
    turns_kept: int
    turns_dropped_duplicate: int
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.original_tokens} -> {self.compressed_tokens} tokens "
            f"({self.compression_ratio * 100:.1f}% reduction), "
            f"{self.turns_kept}/{self.turns_total} turns kept, "
            f"{self.turns_dropped_duplicate} duplicate turn(s) dropped"
        )

    def to_messages(self) -> List[Dict[str, str]]:
        """Reconstruct a plain [{role, content}, ...] transcript from the
        surviving turns, in original order, e.g. to feed back into an
        API call."""
        return [{"role": t.role, "content": t.content} for t in self.turns if t.action != "dropped_duplicate"]


# --------------------------------------------------------------------------
# Format detection / parsing
# --------------------------------------------------------------------------

def _flatten_content(content: Any) -> str:
    """Normalize the many shapes 'message content' shows up in across
    export formats into a single string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Anthropic-style content blocks: [{"type": "text", "text": "..."}]
        # or ChatGPT "parts": ["..."]
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    parts.append(str(item["text"]))
                elif "text" in item:
                    parts.append(str(item["text"]))
                elif item.get("type") in ("tool_use", "tool_result"):
                    # Keep a compact marker rather than dumping raw tool
                    # payloads (often large JSON blobs, low text-density).
                    parts.append(f"[{item.get('type')}: {item.get('name', '')}]".strip())
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _parse_generic(data: Any) -> Optional[List[Turn]]:
    """A plain list of {"role": ..., "content": ...} dicts -- the shape
    of an OpenAI/Anthropic API `messages` array, and the simplest thing
    to hand-author for testing."""
    if not isinstance(data, list) or not data:
        return None
    turns = []
    for item in data:
        if not isinstance(item, dict) or "role" not in item:
            return None
        turns.append(Turn(role=item["role"], content=_flatten_content(item.get("content", ""))))
    return turns


def _parse_chatgpt_export(data: Any) -> Optional[List[Turn]]:
    """ChatGPT's `conversations.json` export: either a single
    conversation object or a list of them (we use the first / longest).
    Each conversation has a `mapping` dict of node-id -> node, where
    each node has a `message` with `author.role` and `content.parts`,
    linked via `parent` pointers."""
    conv = None
    if isinstance(data, dict) and "mapping" in data:
        conv = data
    elif isinstance(data, list):
        candidates = [d for d in data if isinstance(d, dict) and "mapping" in d]
        if candidates:
            conv = max(candidates, key=lambda c: len(c.get("mapping", {})))
    if conv is None:
        return None

    mapping = conv["mapping"]
    # Walk from the "current_node" (or any leaf) back to the root via
    # parent pointers to get a single linear transcript -- ChatGPT
    # exports are technically a tree (regenerations branch), we only
    # want the final/live branch.
    node_id = conv.get("current_node")
    if node_id is None or node_id not in mapping:
        # fall back: any node with no children
        child_ids = {c for n in mapping.values() for c in (n.get("children") or [])}
        leaves = [nid for nid in mapping if nid not in child_ids]
        node_id = leaves[0] if leaves else next(iter(mapping), None)
    if node_id is None:
        return None

    chain = []
    seen = set()
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(mapping[node_id])
        node_id = mapping[node_id].get("parent")
    chain.reverse()

    turns = []
    for node in chain:
        msg = node.get("message")
        if not msg:
            continue
        role = (msg.get("author") or {}).get("role")
        if role not in ("system", "user", "assistant", "tool"):
            continue
        content = msg.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        text = _flatten_content(parts if parts is not None else content)
        if not text.strip():
            continue
        turns.append(Turn(role=role, content=text))
    return turns or None


def _parse_claude_export(data: Any) -> Optional[List[Turn]]:
    """claude.ai conversation export: a dict (or list of one) with a
    `chat_messages` array, each having `sender` ("human"/"assistant")
    and `text` (or `content` blocks)."""
    conv = None
    if isinstance(data, dict) and "chat_messages" in data:
        conv = data
    elif isinstance(data, list):
        candidates = [d for d in data if isinstance(d, dict) and "chat_messages" in d]
        if candidates:
            conv = max(candidates, key=lambda c: len(c.get("chat_messages", [])))
    if conv is None:
        return None

    role_map = {"human": "user", "assistant": "assistant", "system": "system"}
    turns = []
    for msg in conv["chat_messages"]:
        sender = msg.get("sender", "user")
        role = role_map.get(sender, sender if sender in ("user", "assistant", "system") else "user")
        text = msg.get("text")
        if not text:
            text = _flatten_content(msg.get("content"))
        if not text or not str(text).strip():
            continue
        turns.append(Turn(role=role, content=str(text)))
    return turns or None


def parse_export(raw: str) -> Tuple[List[Turn], str]:
    """Parse a conversation export (as raw JSON text) into a list of
    Turns, auto-detecting the source format.

    Returns (turns, format_name) where format_name is one of
    "chatgpt", "claude", "generic".

    Raises ValueError if the JSON can't be parsed into any known shape.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid JSON: {e}")

    for parser, name in (
        (_parse_chatgpt_export, "chatgpt"),
        (_parse_claude_export, "claude"),
        (_parse_generic, "generic"),
    ):
        turns = parser(data)
        if turns:
            return turns, name

    raise ValueError(
        "unrecognized conversation export format -- expected a ChatGPT "
        "conversations.json export, a claude.ai conversation export, or "
        "a generic [{'role': ..., 'content': ...}, ...] list"
    )


# --------------------------------------------------------------------------
# Compression
# --------------------------------------------------------------------------

def compress_session(
    raw_export: str,
    protect_recent: int = 4,
    target_compression: float = 0.70,
    model: str = "default",
    dedup_threshold: Optional[float] = 0.9,
    min_turn_tokens: int = 20,
) -> SessionCompressionReport:
    """
    Compress a chat/conversation export.

    protect_recent: number of most-recent turns (messages) to always
        keep verbatim, in addition to any system prompt. Counted from
        the end of the transcript.
    target_compression: fraction of tokens to remove from each
        *compressible* (older, non-system) turn -- same meaning as
        ContextCompressor's target_compression.
    dedup_threshold: cosine-similarity cutoff above which two older
        turns of the same role are considered duplicates and the later
        one is dropped. Pass None for adaptive.
    min_turn_tokens: turns shorter than this are left untouched even
        if they're outside the protected window -- compressing a
        3-token "yes" or "sounds good" wastes a compression pass for
        zero savings.
    """
    turns, _fmt = parse_export(raw_export)
    n = len(turns)

    system_idx = {i for i, t in enumerate(turns) if t.role == "system"}
    non_system_idx = [i for i in range(n) if i not in system_idx]
    protected_recent_idx = set(non_system_idx[-protect_recent:]) if protect_recent > 0 else set()

    compressible_idx = [i for i in range(n) if i not in system_idx and i not in protected_recent_idx]

    # Near-duplicate whole-turn removal among compressible turns, done
    # per-role so a repeated user question isn't compared against
    # assistant replies.
    dropped: set = set()
    if len(compressible_idx) > 1:
        by_role: Dict[str, List[int]] = {}
        for i in compressible_idx:
            by_role.setdefault(turns[i].role, []).append(i)
        for role, idxs in by_role.items():
            if len(idxs) < 2:
                continue
            texts = [turns[i].content for i in idxs]
            _kept_texts, dropped_local = remove_near_duplicates(texts, dedup_threshold)
            for local_i in dropped_local:
                dropped.add(idxs[local_i])

    compressor = ContextCompressor(target_compression=target_compression, model=model)

    turn_reports: List[TurnReport] = []
    total_original = 0
    total_compressed = 0
    kept_count = 0
    dup_count = 0

    for i, t in enumerate(turns):
        orig_tokens = count_tokens(t.content, model=model)
        total_original += orig_tokens

        if i in system_idx:
            turn_reports.append(TurnReport("system", orig_tokens, orig_tokens, "protected_system", t.content))
            total_compressed += orig_tokens
            kept_count += 1
            continue

        if i in dropped:
            turn_reports.append(TurnReport(t.role, orig_tokens, 0, "dropped_duplicate", ""))
            dup_count += 1
            continue

        if i in protected_recent_idx:
            turn_reports.append(TurnReport(t.role, orig_tokens, orig_tokens, "protected_recent", t.content))
            total_compressed += orig_tokens
            kept_count += 1
            continue

        if orig_tokens < min_turn_tokens:
            turn_reports.append(TurnReport(t.role, orig_tokens, orig_tokens, "compressed", t.content))
            total_compressed += orig_tokens
            kept_count += 1
            continue

        report = compressor.compress(t.content, content_type="prose")
        turn_reports.append(TurnReport(t.role, orig_tokens, report.compressed_tokens, "compressed", report.compressed_text))
        total_compressed += report.compressed_tokens
        kept_count += 1

    ratio = 1 - (total_compressed / total_original) if total_original else 0.0

    notes = [
        f"parsed {n} turn(s) as '{_fmt}' format",
        f"protected {len(system_idx)} system turn(s) + {len(protected_recent_idx)} recent turn(s) verbatim",
        f"dropped {dup_count} duplicate older turn(s)",
        f"compressed {kept_count - len(system_idx) - len(protected_recent_idx)} older turn(s)",
    ]

    return SessionCompressionReport(
        turns=turn_reports,
        original_tokens=total_original,
        compressed_tokens=total_compressed,
        compression_ratio=max(0.0, ratio),
        turns_total=n,
        turns_kept=kept_count,
        turns_dropped_duplicate=dup_count,
        notes=[n_ for n_ in notes if n_],
    )
