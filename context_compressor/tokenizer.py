"""
Lightweight token counting.

Tries tiktoken (accurate BPE counts) first. If tiktoken's encoding files
can't be fetched (e.g. no network access to its CDN), falls back to a
regex-based approximation that is close enough for measuring compression
ratios (it doesn't need to be exact -- before/after counts just need to
be consistent with each other).

Different target models use different tokenizers, so what "70% smaller"
means in absolute API cost/latency terms differs by model family. This
module lets callers pick an approximate tokenizer profile per target
model rather than always assuming GPT-style cl100k_base.
"""

import re

# Model family -> (tiktoken encoding name or None, chars-per-token
# heuristic used for the non-tiktoken fallback/approximation).
_MODEL_PROFILES = {
    "gpt-4": ("cl100k_base", 4.0),
    "gpt-4o": ("o200k_base", 4.0),
    "gpt-3.5": ("cl100k_base", 4.0),
    "claude": (None, 3.8),   # Claude's tokenizer isn't public via tiktoken;
                              # 3.8 chars/token is a commonly used approximation
    "gemini": (None, 4.0),
    "default": ("cl100k_base", 4.0),
}

_encoders = {}


def _get_tiktoken(encoding_name):
    if encoding_name is None:
        return None
    if encoding_name in _encoders:
        return _encoders[encoding_name]
    try:
        import tiktoken

        enc = tiktoken.get_encoding(encoding_name)
    except Exception:
        enc = None
    _encoders[encoding_name] = enc
    return enc


_WORD_RE = re.compile(r"\S+")


def count_tokens(text: str, model: str = "default") -> int:
    """Return an approximate token count for `text`.

    model: one of the keys in _MODEL_PROFILES (e.g. "gpt-4", "claude",
    "gemini"), or "default". Unknown values fall back to "default".
    """
    if not text:
        return 0

    encoding_name, chars_per_token = _MODEL_PROFILES.get(model, _MODEL_PROFILES["default"])

    enc = _get_tiktoken(encoding_name)
    if enc is not None:
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass

    # Fallback 1: character-based estimate using the model's approximate
    # chars-per-token ratio -- more model-aware than a flat word count.
    if chars_per_token:
        char_estimate = max(1, round(len(text) / chars_per_token))
    else:
        char_estimate = None

    # Fallback 2: whitespace-split words, roughly ~1.3 tokens per word
    # for English/code text (rough GPT-style heuristic). Used as a
    # sanity blend so very short/long-word text doesn't skew badly.
    words = len(_WORD_RE.findall(text))
    word_estimate = max(1, round(words * 1.3)) if words else 0

    if char_estimate is None:
        return word_estimate
    if word_estimate == 0:
        return char_estimate
    return round((char_estimate + word_estimate) / 2)


def supported_models():
    return list(_MODEL_PROFILES.keys())
