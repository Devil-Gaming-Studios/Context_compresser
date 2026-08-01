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

from typing import List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def remove_near_duplicates(
    chunks: List[str], threshold: float = 0.85
) -> Tuple[List[str], List[int]]:
    """
    Returns (kept_chunks, dropped_indices).

    Greedy pass: for each chunk (in order), drop it if it's too similar
    to any chunk already kept.
    """
    n = len(chunks)
    if n <= 1:
        return list(chunks), []

    non_trivial_idx = [i for i, c in enumerate(chunks) if len(c.strip()) >= 3]
    if len(non_trivial_idx) <= 1:
        return list(chunks), []

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
