from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .crawler import NewsItem


_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "new",
    "of",
    "on",
    "or",
    "release",
    "released",
    "launch",
    "launched",
    "introduce",
    "introduces",
    "introducing",
    "tool",
    "tools",
    "ai",
    "the",
    "to",
    "with",
    "your",
}


def _title_candidates(title: str) -> list[str]:
    title = " ".join((title or "").split()).strip()
    if not title:
        return []

    cands: list[str] = []

    # Pull quoted names first
    for m in re.finditer(r"[\"“”']([^\"“”']{3,60})[\"“”']", title):
        q = m.group(1).strip()
        if q and len(q) <= 40:
            cands.append(q)

    # Capitalized phrases: "Foo Bar", "OpenAI", "Llama 3.2"
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9.+-]{1,}(?:\s+[A-Z0-9][A-Za-z0-9.+-]{1,}){0,3})\b", title):
        phrase = " ".join(m.group(1).split()).strip()
        if 3 <= len(phrase) <= 40:
            cands.append(phrase)

    # Token fallback: long-ish words
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]{2,}", title)
    for t in tokens:
        if t.lower() in _STOP:
            continue
        if t.isdigit():
            continue
        if 3 <= len(t) <= 24:
            cands.append(t)

    # Cleanup
    out: list[str] = []
    seen: set[str] = set()
    for s in cands:
        s = s.strip(" -–—:|,.;")
        if not s:
            continue
        key = s.lower()
        if key in _STOP:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def discover_topics_from_items(items: Iterable[NewsItem], *, limit: int = 30) -> list[str]:
    """
    Returns a ranked list of candidate topic tags extracted from page titles (headline mode or creative/story mode).
    """
    counter: Counter[str] = Counter()
    original: dict[str, str] = {}
    for it in items:
        for cand in _title_candidates(it.title):
            key = cand.lower()
            counter[key] += 1
            # preserve a nicely-cased exemplar
            original.setdefault(key, cand)

    ranked = [original[k] for k, _ in counter.most_common()]
    # Prefer multi-word phrases over single tokens when tied
    ranked.sort(key=lambda s: (-min(4, counter[s.lower()]), -s.count(" "), s.lower()))

    out: list[str] = []
    seen: set[str] = set()
    for s in ranked:
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= max(1, int(limit)):
            break
    return out

