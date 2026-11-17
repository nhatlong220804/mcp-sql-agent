"""Text chunking.

Word windows with overlap, nudged to end on a sentence boundary when one is close
enough. Nothing clever, but the chunk size matters more than the strategy and the
benchmark script covers that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WORD = re.compile(r"\S+")
SENTENCE_END = re.compile(r"[.!?]\s*$")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start_word: int
    end_word: int


def split_words(text: str) -> list[str]:
    return WORD.findall(text)


def chunk_text(text: str, size: int = 512, overlap: int = 64) -> list[Chunk]:
    """Split text into overlapping windows of `size` words.

    Args:
        text: source document.
        size: words per chunk.
        overlap: words shared with the next chunk.

    Raises:
        ValueError: if overlap is not smaller than size.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")

    words = split_words(text)
    if not words:
        return []

    chunks: list[Chunk] = []
    start = 0
    step = size - overlap

    while start < len(words):
        end = min(start + size, len(words))

        # if a sentence ends within the last 15% of the window, cut there instead
        if end < len(words):
            lookback = max(start + int(size * 0.85), start + 1)
            for cut in range(end, lookback - 1, -1):
                if SENTENCE_END.search(words[cut - 1]):
                    end = cut
                    break

        chunks.append(
            Chunk(
                index=len(chunks),
                text=" ".join(words[start:end]),
                start_word=start,
                end_word=end,
            )
        )

        if end >= len(words):
            break
        start = max(end - overlap, start + step if overlap == 0 else start + step)
        # keep monotonic progress even when a sentence cut shortened the window
        if start <= chunks[-1].start_word:
            start = chunks[-1].start_word + step

    return chunks
