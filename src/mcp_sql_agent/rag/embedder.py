"""TF-IDF index in numpy.

Deliberately no embedding API. The server has to work on a laptop with no network
and no key, and for a corpus of a few hundred policy paragraphs lexical retrieval is
good enough to demonstrate the pipeline. Swap `TfidfIndex` for a real embedding
model by keeping the same `search` signature.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """
    a an and are as at be been by for from has have if in into is it its of on or
    that the their then there these they this to was were will with
    """.split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


class TfidfIndex:
    def __init__(self, documents: list[str]):
        if not documents:
            raise ValueError("index needs at least one document")

        self._tokenised = [tokenize(d) for d in documents]
        self._vocab: dict[str, int] = {}

        df = Counter()
        for tokens in self._tokenised:
            for term in set(tokens):
                df[term] += 1

        for term in sorted(df):
            self._vocab[term] = len(self._vocab)

        n_docs = len(documents)
        self._idf = np.zeros(len(self._vocab), dtype=np.float32)
        for term, idx in self._vocab.items():
            self._idf[idx] = math.log((1 + n_docs) / (1 + df[term])) + 1.0

        matrix = np.zeros((n_docs, len(self._vocab)), dtype=np.float32)
        for row, tokens in enumerate(self._tokenised):
            if not tokens:
                continue
            counts = Counter(tokens)
            length = len(tokens)
            for term, count in counts.items():
                col = self._vocab.get(term)
                if col is not None:
                    matrix[row, col] = (count / length) * self._idf[col]

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms

    @property
    def vocabulary_size(self) -> int:
        return len(self._vocab)

    def vectorize(self, text: str) -> np.ndarray:
        tokens = tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        if not tokens:
            return vec
        counts = Counter(tokens)
        length = len(tokens)
        for term, count in counts.items():
            col = self._vocab.get(term)
            if col is not None:
                vec[col] = (count / length) * self._idf[col]
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        """Return (row_index, cosine_score) for the top k documents."""
        q = self.vectorize(query)
        if not q.any():
            return []
        scores = self._matrix @ q
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]
