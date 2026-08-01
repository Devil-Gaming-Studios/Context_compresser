"""
Lightweight token counting.

Tries tiktoken (accurate BPE counts) first. If tiktoken's encoding files
can't be fetched (e.g. no network access to its CDN), falls back to a
regex-based approximation that is close enough for measuring compression
ratios (it doesn't need to be exact -- before/after counts just need to
be consistent with each other).
"""

import re

_tiktoken_encoder = None
_tiktoken_checked = False


def _get_tiktoken():
    global _tiktoken_encoder, _tiktoken_checked
    if _tiktoken_checked:
        return _tiktoken_encoder
    _tiktoken_checked = True
    try:
        import tiktoken

        _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tiktoken_encoder = None
    return _tiktoken_encoder


_WORD_RE = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """Return an approximate token count for `text`."""
    if not text:
        return 0

    enc = _get_tiktoken()
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass

    # Fallback: whitespace-split words, roughly ~0.75 tokens per word
    # for English/code text (rough GPT-style heuristic).
    words = len(_WORD_RE.findall(text))
    return max(1, round(words * 1.3)) if words else 0
