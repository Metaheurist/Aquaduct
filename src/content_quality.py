from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .crawler import NewsItem


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]{1,}")


def _tokens(s: str) -> set[str]:
    toks = [t.lower() for t in _TOKEN_RE.findall(s or "")]
    stop = {
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
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "new",
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
    }
    return {t for t in toks if t not in stop and len(t) >= 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return (inter / float(union)) if union else 0.0


def _looks_clickbaity(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return True
    if t.count("!") >= 2:
        return True
    if "you won't believe" in t or "this one trick" in t:
        return True
    if len(t) < 18:
        return True
    return False


def _impact_keywords_score(title: str) -> float:
    t = (title or "").lower()
    boosts = {
        "launch": 0.6,
        "launched": 0.6,
        "release": 0.6,
        "released": 0.6,
        "introduces": 0.5,
        "open-source": 0.5,
        "open source": 0.5,
        "funding": 0.4,
        "raises": 0.4,
        "acquires": 0.4,
        "acquisition": 0.4,
        "breakthrough": 0.4,
        "beats": 0.3,
        "adds": 0.3,
        "announces": 0.3,
        "ships": 0.3,
    }
    s = 0.0
    for k, v in boosts.items():
        if k in t:
            s += v
    # Named-entity-ish boost: presence of capitalized phrases in original title
    caps = re.findall(r"\b[A-Z][A-Za-z0-9.+-]{2,}\b", title or "")
    if caps:
        s += min(0.7, 0.1 * len(set(caps)))
    return min(1.5, s)


def _tag_match_score(title: str, topic_tags: Iterable[str] | None) -> float:
    if not topic_tags:
        return 0.0
    tl = (title or "").lower()
    hits = 0
    for t in topic_tags:
        t = (t or "").strip().lower()
        if not t:
            continue
        if t in tl:
            hits += 1
    return min(1.0, 0.25 * hits)


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    novelty: float
    impact: float
    clarity: float
    recency: float
    source: float
    tag_match: float
    duplicate_penalty: float


def score_item(
    item: NewsItem,
    *,
    topic_tags: list[str] | None,
    seen_titles: list[str] | None,
    source_weights: dict[str, float] | None = None,
) -> ScoreBreakdown:
    title = (item.title or "").strip()
    toks = _tokens(title)

    novelty = 1.0
    duplicate_penalty = 0.0
    if seen_titles:
        sims = []
        for s in seen_titles[-200:]:
            sims.append(_jaccard(toks, _tokens(s)))
        sim = max(sims) if sims else 0.0
        novelty = max(0.0, 1.0 - sim)
        if sim >= 0.72:
            duplicate_penalty = 1.0

    impact = _impact_keywords_score(title)
    clarity = 0.0 if _looks_clickbaity(title) else 1.0
    # Recency is weakly used because many sources don’t provide pubDate; keep neutral.
    recency = 0.3 if getattr(item, "published_at", None) else 0.0

    source_w = 0.0
    if source_weights:
        source_w = float(source_weights.get((item.source or "").strip(), 0.0))

    tag_match = _tag_match_score(title, topic_tags)

    total = (
        1.25 * novelty
        + 1.10 * impact
        + 0.70 * clarity
        + 0.25 * recency
        + 0.45 * source_w
        + 0.60 * tag_match
        - 2.0 * duplicate_penalty
    )
    # squash to something stable-ish for UI display
    total = float(max(-2.0, min(5.0, total)))
    return ScoreBreakdown(
        total=total,
        novelty=float(novelty),
        impact=float(impact),
        clarity=float(clarity),
        recency=float(recency),
        source=float(source_w),
        tag_match=float(tag_match),
        duplicate_penalty=float(duplicate_penalty),
    )


def diversify(items: list[NewsItem], *, topic_tags: list[str] | None, k: int) -> list[NewsItem]:
    """
    Best-effort diversification: if tags exist, attempt to include multiple tag clusters.
    """
    items = list(items or [])
    if not items:
        return []
    k = max(1, int(k))
    if not topic_tags:
        return items[:k]

    tags = [t.strip().lower() for t in (topic_tags or []) if t and t.strip()]
    if not tags:
        return items[:k]

    buckets: dict[str, list[NewsItem]] = {t: [] for t in tags[:12]}
    other: list[NewsItem] = []
    for it in items:
        tl = (it.title or "").lower()
        placed = False
        for t in buckets.keys():
            if t in tl:
                buckets[t].append(it)
                placed = True
                break
        if not placed:
            other.append(it)

    out: list[NewsItem] = []
    # round-robin buckets
    while len(out) < k:
        progressed = False
        for t in list(buckets.keys()):
            if buckets[t]:
                out.append(buckets[t].pop(0))
                progressed = True
                if len(out) >= k:
                    break
        if len(out) >= k:
            break
        if other:
            out.append(other.pop(0))
            progressed = True
        if not progressed:
            break
    return out[:k]


def load_seen_titles(path: Path) -> list[str]:
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            out = [str(x) for x in data if isinstance(x, str) and x.strip()]
            return out[-5000:]
        return []
    except Exception:
        return []


def save_seen_titles(path: Path, titles: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = [t for t in (titles or []) if isinstance(t, str) and t.strip()][-5000:]
        path.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

