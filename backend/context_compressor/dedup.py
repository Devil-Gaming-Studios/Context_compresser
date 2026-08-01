"""
Semantic-ish near-duplicate removal.

Uses TF-IDF cosine similarity between chunks (sentences/lines) rather
than a downloaded embedding model, so it runs fully offline. Two chunks
above `threshold` similarity are treated as saying "the same thing" --
we keep the first (usually the more complete) occurrence and drop the
rest.

This catches paraphrase-lite redundancy (e.g. a function re-explained
in a comment right above its definition, or a log message repeated with
slightly different wording) that exact-match dedup in boilerplate.py
misses.
"""

from typing import List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def adaptive_threshold(chunks: List[str], percentile: float = 95.0, floor: float = 0.6, ceiling: float = 0.95) -> float:
    """
    Compute a dedup similarity threshold from the document's own
    pairwise-similarity distribution instead of using a fixed constant.

    A fixed threshold (e.g. 0.85) behaves inconsistently across very
    different documents: a terse log file's lines are naturally more
    similar to each other than prose paragraphs are, so the same cutoff
    is "aggressive" in one document and "barely triggers" in another.
    Using a high percentile (default: 95th) of the document's actual
    similarity distribution adapts to that automatically -- it targets
    "the top slice of pairs that are unusually similar for THIS
    document" rather than an arbitrary absolute number.
    """
    non_trivial = [c for c in chunks if len(c.strip()) >= 3]
    if len(non_trivial) <= 2:
        return floor

    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w[\w\-\.]*\b")
    try:
        matrix = vectorizer.fit_transform(non_trivial)
    except ValueError:
        return floor

    sim = cosine_similarity(matrix)
    n = sim.shape[0]
    upper = sim[np.triu_indices(n, k=1)]
    if upper.size == 0:
        return floor

    value = float(np.percentile(upper, percentile))
    return float(np.clip(value, floor, ceiling))


def remove_near_duplicates(
    chunks: List[str], threshold: Optional[float] = 0.85
) -> Tuple[List[str], List[int]]:
    """
    Returns (kept_chunks, dropped_indices).

    Greedy pass: for each chunk (in order), drop it if it's too similar
    to any chunk already kept.

    threshold: fixed cosine-similarity cutoff. Pass None to compute an
    adaptive threshold from this document's own similarity distribution
    (see `adaptive_threshold`) instead of using a fixed constant.
    """
    n = len(chunks)
    if n <= 1:
        return list(chunks), []

    non_trivial_idx = [i for i, c in enumerate(chunks) if len(c.strip()) >= 3]
    if len(non_trivial_idx) <= 1:
        return list(chunks), []

    if threshold is None:
        threshold = adaptive_threshold(chunks)

    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w[\w\-\.]*\b")
    try:
        matrix = vectorizer.fit_transform([chunks[i] for i in non_trivial_idx])
    except ValueError:
        return list(chunks), []

    sim = cosine_similarity(matrix)

    kept_local = []
    dropped_local = []
    for local_i in range(len(non_trivial_idx)):
        is_dup = False
        for kept_j in kept_local:
            if sim[local_i, kept_j] >= threshold:
                is_dup = True
                break
        if is_dup:
            dropped_local.append(local_i)
        else:
            kept_local.append(local_i)

    dropped_global = {non_trivial_idx[j] for j in dropped_local}
    kept_chunks = [c for i, c in enumerate(chunks) if i not in dropped_global]
    dropped_indices = sorted(dropped_global)
    return kept_chunks, dropped_indices
