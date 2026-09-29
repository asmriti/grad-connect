"""Text chunking for embeddings.

Chunks target ~CHUNK_SIZE tokens with ~CHUNK_OVERLAP token overlap
(approximated as 4 characters per token, which is close enough for English
prose and avoids a tokenizer dependency here). Chunks are built from the
extractor's heading-grouped sections, splitting on sentence boundaries where
reasonably possible, and each chunk carries its section heading so it is
meaningful on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CHARS_PER_TOKEN = 4

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9À-ɏ\"'(])")


@dataclass
class Chunk:
    text: str
    heading: str | None
    chunk_index: int


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts.extend(s for s in _SENTENCE_RE.split(line) if s.strip())
    return parts


def _pack(sentences: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    """Pack sentences into chunks of <= max_chars with sentence-level overlap."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        # A single sentence longer than max_chars gets hard-split.
        while len(sentence) > max_chars:
            head, sentence = sentence[:max_chars], sentence[max_chars - overlap_chars:]
            if current:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            chunks.append(head)
        if current_len + len(sentence) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            # Overlap: carry trailing sentences into the next chunk.
            carried: list[str] = []
            carried_len = 0
            for prev in reversed(current):
                if carried_len + len(prev) + 1 > overlap_chars:
                    break
                carried.insert(0, prev)
                carried_len += len(prev) + 1
            current, current_len = carried, carried_len
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_sections(
    sections: list,  # list of objects with .heading and .text
    chunk_size_tokens: int,
    overlap_tokens: int,
    min_chunk_chars: int = 60,
) -> list[Chunk]:
    """Chunk a page's sections. Sections shorter than the chunk size are kept
    whole (never split mid-section); long sections are split on sentence
    boundaries with overlap. Each chunk is prefixed with its heading so the
    embedding sees the context (e.g. "Research Interests")."""
    max_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    chunks: list[Chunk] = []
    index = 0
    for section in sections:
        heading = (section.heading or "").strip() or None
        body = section.text.strip()
        if not body:
            continue
        prefix = f"{heading}\n\n" if heading else ""
        budget = max_chars - len(prefix)
        if len(body) <= budget:
            pieces = [body]
        else:
            pieces = _pack(_split_sentences(body), budget, overlap_chars)
        for piece in pieces:
            text = prefix + piece
            if len(text) < min_chunk_chars:
                continue  # skip fragments too small to carry meaning
            chunks.append(Chunk(text=text, heading=heading, chunk_index=index))
            index += 1
    return chunks
