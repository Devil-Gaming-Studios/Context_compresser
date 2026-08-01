"""
Information-density scoring for extractive compression.

We use TF-IDF over the chunk set (sentences or lines) as a proxy for how
much unique information each chunk carries relative to the rest of the
document. Chunks that are rare/distinctive score high; chunks that are
generic or repeat vocabulary already covered score low.

This avoids any downloaded embedding model -- it's pure statistics over
the document itself, so it works fully offline.
"""

from typing import List
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Generic filler/boilerplate phrases that should never rank as "important"
# even if they're statistically rare in a short document.
_FILLER_PATTERNS = [
    r"^\s*#.*$",                      # bare comment-only lines (code)
    r"^\s*//.*$",
    r"^\s*(import|from)\s+\S+",       # import statements
    r"^\s*(using|package)\s+\S+",
    r"^\s*\{?\s*\}?\s*$",             # stray braces
    r"^\s*(pass|continue|break)\s*$",
    r"^\s*(INFO|DEBUG)\b.*heartbeat.*$",
]
_FILLER_RE = [re.compile(p, re.IGNORECASE) for p in _FILLER_PATTERNS]


def _is_filler(chunk: str) -> bool:
    return any(p.match(chunk) for p in _FILLER_RE)


def score_chunks(chunks: List[str]) -> np.ndarray:
    """
    Return an information-density score per chunk (higher = keep).

    Score = TF-IDF mass of the chunk (sum of tf-idf weights of its terms),
    normalized by chunk length so long chunks don't win purely on size,
    then penalized if the chunk matches a known filler pattern.
    """
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
        if _is_filler(c):
            density[i] *= 0.1

    # Penalize near-empty chunks
    for i, c in enumerate(chunks):
        if len(c.strip()) < 3:
            density[i] = 0.0

    return density
