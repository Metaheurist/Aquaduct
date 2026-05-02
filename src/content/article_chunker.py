"""Sentence-aware chunking for the article-relevance LLM pass.

The relevance pass runs one chunk at a time, sharing the LLM holder across
chunks and across other pipeline stages, so we keep individual prompts well
inside the model's context window. We chunk on sentence boundaries first
(`. ! ?`), then on paragraph breaks, then fall back to a hard cut.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_SENT_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_PARA_RE = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class ArticleChunk:
    index: int
    text: str
    char_start: int
    char_end: int

    @property
    def length(self) -> int:
        return len(self.text)


def _split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = _SENT_END_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_article_text(
    text: str,
    *,
    target_chars: int = 1800,
    max_chunks: int = 8,
    min_chars: int = 100,
) -> list[ArticleChunk]:
    """Return a small list of sentence-aware chunks (capped at ``max_chunks``).

    The default ``target_chars=1800`` is well inside the 4k-context window
    of common 8B chat models even with a fairly long system prompt.
    """
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARA_RE.split(text) if p and p.strip()]
    if not paragraphs:
        paragraphs = [text]

    sentences: list[str] = []
    for p in paragraphs:
        sub = _split_sentences(p)
        if sub:
            sentences.extend(sub)
        else:
            sentences.append(p)

    chunks: list[ArticleChunk] = []
    cur: list[str] = []
    cur_len = 0
    char_cursor = 0

    def _flush(start_offset: int) -> None:
        nonlocal cur, cur_len, char_cursor
        if not cur:
            return
        body = " ".join(cur).strip()
        if not body:
            cur = []
            cur_len = 0
            return
        end_offset = start_offset + len(body)
        chunks.append(
            ArticleChunk(
                index=len(chunks),
                text=body,
                char_start=start_offset,
                char_end=end_offset,
            )
        )
        cur = []
        cur_len = 0

    start = 0
    for s in sentences:
        if cur_len + len(s) + 1 > target_chars and cur:
            _flush(start)
            start = char_cursor
            if len(chunks) >= max_chunks:
                break
        cur.append(s)
        cur_len += len(s) + 1
        char_cursor += len(s) + 1
    if cur and len(chunks) < max_chunks:
        _flush(start)

    if chunks and chunks[0].length < min_chars and len(chunks) >= 2:
        first, second = chunks[0], chunks[1]
        merged = ArticleChunk(
            index=0,
            text=(first.text + " " + second.text).strip(),
            char_start=first.char_start,
            char_end=second.char_end,
        )
        chunks = [merged] + chunks[2:]
        for i, c in enumerate(chunks):
            chunks[i] = ArticleChunk(
                index=i, text=c.text, char_start=c.char_start, char_end=c.char_end
            )
    return chunks
