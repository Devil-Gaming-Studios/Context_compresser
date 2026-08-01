"""
Information-density scoring for extractive compression.

We use TF-IDF over the chunk set (sentences or lines) as a proxy for how
much unique information each chunk carries relative to the rest of the
document. Chunks that are rare/distinctive score high; chunks that are
generic or repeat vocabulary already covered score low.

This avoids any downloaded embedding model -- it's pure statistics over
the document itself, so it works fully offline.
"""

from typing import List, Optional, Sequence
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Generic filler/boilerplate phrases that should never rank as "important"
# even if they're statistically rare in a short document. Callers can
# extend or fully replace this list via `score_chunks(..., filler_patterns=...)`
# / `ContextCompressor(extra_filler_patterns=[...])` for domain-specific
# noise (e.g. a company's own heartbeat/health-check log format).
DEFAULT_FILLER_PATTERNS = [
    r"^\s*#.*$",                      # bare comment-only lines (code)
    r"^\s*//.*$",
    r"^\s*(import|from)\s+\S+",       # import statements
    r"^\s*(using|package)\s+\S+",
    r"^\s*\{?\s*\}?\s*$",             # stray braces
    r"^\s*(pass|continue|break)\s*$",
    r"^\s*(INFO|DEBUG)\b.*heartbeat.*$",
]


def _compile_filler(patterns: Sequence[str]):
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _is_filler(chunk: str, filler_re) -> bool:
    return any(p.match(chunk) for p in filler_re)


def score_chunks(
    chunks: List[str],
    filler_patterns: Optional[Sequence[str]] = None,
    force_keep: Optional[set] = None,
) -> np.ndarray:
    """
    Return an information-density score per chunk (higher = keep).

    Score = TF-IDF mass of the chunk (sum of tf-idf weights of its terms),
    normalized by chunk length so long chunks don't win purely on size,
    then penalized if the chunk matches a known filler pattern.

    filler_patterns: regex list overriding DEFAULT_FILLER_PATTERNS. Pass
        None to use the defaults.
    force_keep: set of chunk indices that should always score at the
        maximum (1.0) regardless of TF-IDF/filler signals -- used for
        code blocks that a dependency-closure pass determined are
        referenced elsewhere and must survive selection.
    """
    filler_re = _compile_filler(filler_patterns if filler_patterns is not None else DEFAULT_FILLER_PATTERNS)

    if len(chunks) == 0:
        return np.array([])
    if len(chunks) == 1:
        return np.array([1.0])

    vectorizer = TfidfVectorizer(
        token_pattern=r"(?u)\b\w[\w\-\.]*\b",
        stop_words="english",
    )
    try:
        tfidf = vectorizer.fit_transform(chunks)
    except ValueError:
        # e.g. all chunks are empty/stopwords-only
        return np.ones(len(chunks))

    raw_scores = np.asarray(tfidf.sum(axis=1)).flatten()

    # Normalize by sqrt(token count) -- rewards density, not just raw length
    lengths = np.array([max(1, len(c.split())) for c in chunks])
    density = raw_scores / np.sqrt(lengths)

    # Rescale to [0, 1]
    if density.max() > 0:
        density = density / density.max()

    # Penalize filler-pattern chunks heavily
    for i, c in enumerate(chunks):
        if _is_filler(c, filler_re):
            density[i] *= 0.1

    # Penalize near-empty chunks
    for i, c in enumerate(chunks):
        if len(c.strip()) < 3:
            density[i] = 0.0

    # Force-keep overrides everything else -- these are chunks a
    # dependency analysis determined are still referenced by other
    # kept chunks (e.g. a helper function called elsewhere), so they
    # must not be starved out by a low TF-IDF score.
    if force_keep:
        for i in force_keep:
            if 0 <= i < len(density):
                density[i] = 1.0

    return density
