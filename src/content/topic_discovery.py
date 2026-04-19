from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .crawler import NewsItem
from .topics import normalize_video_format

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

# Single-token “topic” suggestions that are usually noise for Cartoon / Unhinged Discover (platforms, listicle glue).
_CREATIVE_SINGLE_JUNK = frozenset(
    {
        "youtube",
        "netflix",
        "instagram",
        "tiktok",
        "twitter",
        "facebook",
        "reddit",
        "linkedin",
        "pinterest",
        "snapchat",
        "show",
        "drama",
        "writing",
        "festival",
        "blog",
        "comedy",
        "sketch",
    }
)

_LISTICLE_OR_CLICKBAIT = re.compile(
    r"\b(top|best)\s*\d+\b|\b\d+\s+(best|ways|things|tips|reasons|sketches|comedians)\b|"
    r"\b(top\s+\d+|#\d+\s+)",
    re.IGNORECASE,
)

_CREATIVE_BOOST_TERMS = (
    "cartoon",
    "animation",
    "animated",
    "meme",
    "absurdist",
    "surreal",
    "parody",
    "webcomic",
    "animatic",
    "unhinged",
    "cursed",
    "brainrot",
    "shitpost",
    "satire",
    "2d",
    "3d",
    "vertical",
    "illustration",
    "character",
)


def _creative_topic_boost(s: str, topic_mode: str | None) -> int:
    m = normalize_video_format(topic_mode or "news")
    if m not in ("cartoon", "unhinged"):
        return 0
    sl = s.lower()
    return sum(2 for w in _CREATIVE_BOOST_TERMS if w in sl)


def _should_discard_creative_candidate(s: str, topic_mode: str | None) -> bool:
    m = normalize_video_format(topic_mode or "news")
    if m not in ("cartoon", "unhinged"):
        return False
    t = " ".join(s.split()).strip()
    if not t:
        return True
    sl = t.lower()
    if _LISTICLE_OR_CLICKBAIT.search(sl):
        return True
    if "photos and videos" in sl or "instagram photos" in sl:
        return True
    words = t.split()
    if len(words) == 1 and words[0].lower() in _CREATIVE_SINGLE_JUNK:
        return True
    # Bare platform / venue lines with no animation signal
    if re.search(
        r"\b(youtube|netflix|instagram|tiktok)\b",
        sl,
    ) and not any(k in sl for k in ("cartoon", "animation", "animated", "meme", "animatic", "webcomic")):
        return True
    return False


def _title_too_generic_for_creative(title: str, topic_mode: str | None) -> bool:
    m = normalize_video_format(topic_mode or "news")
    if m not in ("cartoon", "unhinged"):
        return False
    sl = (title or "").lower()
    if _LISTICLE_OR_CLICKBAIT.search(sl):
        return True
    if "photos and videos" in sl or "instagram photos" in sl:
        return True
    return False


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

    # Lowercase / meme-style phrases (Firecrawl often returns sentence-case or all-lowercase titles).
    tl = title.lower()
    for m in re.finditer(r"\b([a-z][a-z']+(?:\s+[a-z][a-z']+){1,5})\b", tl):
        phrase = " ".join(m.group(1).split()).strip()
        if len(phrase) < 8 or len(phrase) > 72:
            continue
        stop_ratio = sum(1 for w in phrase.split() if w in _STOP) / max(1, len(phrase.split()))
        if stop_ratio > 0.45:
            continue
        cands.append(phrase.title())

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


def _fallback_topics_from_titles(
    items: list[NewsItem], *, limit: int, topic_mode: str | None = None
) -> list[str]:
    """When token/phrase heuristics yield nothing, use trimmed page titles as topic lines."""
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        t = " ".join((it.title or "").split()).strip()
        if len(t) < 4:
            continue
        if _title_too_generic_for_creative(t, topic_mode):
            continue
        if len(t) > 120:
            t = t[:117].rstrip() + "…"
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= max(1, int(limit)):
            break
    if not out and items and normalize_video_format(topic_mode or "news") in ("cartoon", "unhinged"):
        # Last resort: still show something if everything was filtered.
        seen2: set[str] = set()
        for it in items:
            t = " ".join((it.title or "").split()).strip()
            if len(t) < 4:
                continue
            if len(t) > 120:
                t = t[:117].rstrip() + "…"
            k = t.lower()
            if k in seen2:
                continue
            seen2.add(k)
            out.append(t)
            if len(out) >= max(1, int(limit)):
                break
    return out


def discover_topics_from_items(
    items: Iterable[NewsItem],
    *,
    limit: int = 30,
    topic_mode: str | None = None,
) -> list[str]:
    """
    Returns a ranked list of candidate topic tags extracted from page titles (news/explainer headlines
    or creative pages from Firecrawl: memes, jokes, stories, art, etc.).
    """
    item_list = list(items)
    counter: Counter[str] = Counter()
    original: dict[str, str] = {}
    for it in item_list:
        for cand in _title_candidates(it.title):
            if _should_discard_creative_candidate(cand, topic_mode):
                continue
            key = cand.lower()
            counter[key] += 1
            # preserve a nicely-cased exemplar
            original.setdefault(key, cand)

    ranked = [original[k] for k, _ in counter.most_common()]
    # Prefer multi-word phrases, animation/meme signal, then frequency
    ranked.sort(
        key=lambda s: (
            -min(4, counter[s.lower()]),
            -s.count(" "),
            -_creative_topic_boost(s, topic_mode),
            s.lower(),
        )
    )

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
    if not out and item_list:
        out = _fallback_topics_from_titles(item_list, limit=limit, topic_mode=topic_mode)
    return out

