from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published_at: str | None = None


def _load_seen(seen_path: Path) -> set[str]:
    if not seen_path.exists():
        return set()
    try:
        data = json.loads(seen_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(x) for x in data)
        return set()
    except Exception:
        return set()


def _save_seen(seen_path: Path, seen: set[str]) -> None:
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the file stable-sized and readable
    trimmed = list(seen)[-5000:]
    seen_path.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")


def _google_news_rss(query: str, limit: int = 3, timeout_s: int = 30) -> list[NewsItem]:
    # Google News RSS query endpoint (no API key)
    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    r = requests.get(url, params=params, timeout=timeout_s, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "xml")
    items: list[NewsItem] = []
    for it in soup.find_all("item")[: max(1, limit)]:
        title = (it.title.text or "").strip()
        link = (it.link.text or "").strip()
        pub = (it.pubDate.text or "").strip() if it.pubDate else None
        source = "GoogleNews"
        if title and link:
            items.append(NewsItem(title=title, url=link, source=source, published_at=pub))
    return items


def _marktechpost_latest(limit: int = 3, timeout_s: int = 30) -> list[NewsItem]:
    # Simple HTML scrape fallback
    r = requests.get(
        "https://www.marktechpost.com/",
        timeout=timeout_s,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    items: list[NewsItem] = []
    # Articles are typically in <article> with <h3>/<h2> links
    for a in soup.select("article a[href]"):
        href = a.get("href", "").strip()
        text = " ".join(a.get_text(" ").split()).strip()
        if not href.startswith("http"):
            continue
        if len(text) < 10:
            continue
        # Heuristic: avoid nav/footer links by requiring marktechpost domain
        if "marktechpost.com" not in href:
            continue
        items.append(NewsItem(title=text, url=href, source="MarkTechPost"))
        if len(items) >= limit:
            break
    return items


def get_latest_items(
    news_cache_dir: Path,
    *,
    limit: int = 3,
    query: str = '("AI tool" OR "AI agent" OR "AI app") (release OR launched OR introduces OR "new tool")',
    topic_tags: list[str] | None = None,
) -> list[NewsItem]:
    """
    Returns up to `limit` fresh items not seen before.
    Dedupes by URL and persists `seen.json`.
    """
    seen_path = news_cache_dir / "seen.json"
    seen = _load_seen(seen_path)

    fetched: list[NewsItem] = []

    # If tags are provided, build a query that biases toward those topics/tools.
    if topic_tags:
        tags = [t.strip() for t in topic_tags if t and t.strip()]
        if tags:
            tag_expr = " OR ".join(f"\"{t}\"" for t in tags[:12])
            query = f"({tag_expr}) (AI OR \"AI tool\" OR \"AI app\") (release OR launched OR introduces OR \"new tool\")"
    # Try RSS first; if it fails, fall back to MarkTechPost.
    try:
        fetched = _google_news_rss(query=query, limit=limit)
    except Exception:
        fetched = []

    if len(fetched) < limit:
        try:
            fetched.extend(_marktechpost_latest(limit=limit - len(fetched)))
        except Exception:
            pass

    # Normalize and filter unseen
    fresh: list[NewsItem] = []
    for item in fetched:
        if item.url in seen:
            continue
        fresh.append(item)
        seen.add(item.url)
        if len(fresh) >= limit:
            break

    _save_seen(seen_path, seen)
    return fresh


def fetch_latest_items(
    *,
    limit: int = 8,
    query: str = '("AI tool" OR "AI agent" OR "AI app") (release OR launched OR introduces OR "new tool")',
    topic_tags: list[str] | None = None,
) -> list[NewsItem]:
    """
    Fetches up to `limit` items from sources WITHOUT applying the seen-cache filter.
    Use this for UI discovery features where "newest headlines" matters more than "unseen".
    """
    fetched: list[NewsItem] = []

    if topic_tags:
        tags = [t.strip() for t in topic_tags if t and t.strip()]
        if tags:
            tag_expr = " OR ".join(f"\"{t}\"" for t in tags[:12])
            query = f"({tag_expr}) (AI OR \"AI tool\" OR \"AI app\") (release OR launched OR introduces OR \"new tool\")"

    try:
        fetched = _google_news_rss(query=query, limit=limit)
    except Exception:
        fetched = []

    if len(fetched) < limit:
        try:
            fetched.extend(_marktechpost_latest(limit=limit - len(fetched)))
        except Exception:
            pass

    # Basic dedupe by URL
    out: list[NewsItem] = []
    seen: set[str] = set()
    for it in fetched:
        if it.url in seen:
            continue
        seen.add(it.url)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def pick_one_item(items: Iterable[NewsItem]) -> NewsItem | None:
    items = list(items)
    if not items:
        return None
    # Simple: newest fetched first.
    return items[0]


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def fetch_article_text(url: str, *, timeout_s: int = 35) -> str:
    """
    Best-effort article text extraction from a URL.
    Intended for lightweight verification/summary; not perfect.
    """
    url = (url or "").strip()
    if not url:
        return ""
    r = requests.get(url, timeout=timeout_s, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    html = r.text or ""
    soup = BeautifulSoup(html, "lxml")

    # Drop obvious junk
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        try:
            tag.decompose()
        except Exception:
            pass

    candidates = []
    for sel in ("article", "main", "div[itemprop='articleBody']", "div.article-content", "div.post-content"):
        try:
            el = soup.select_one(sel)
            if el:
                candidates.append(el.get_text(" ", strip=True))
        except Exception:
            continue

    if not candidates:
        candidates.append(soup.get_text(" ", strip=True))

    # Pick the longest candidate
    text = max(candidates, key=lambda s: len(s or "")) if candidates else ""
    text = " ".join((text or "").split()).strip()
    # Cap size to keep LLM prompts bounded
    return text[:10000]


def get_scored_items(
    news_cache_dir: Path,
    *,
    limit: int = 3,
    fetch_n: int = 16,
    query: str = '("AI tool" OR "AI agent" OR "AI app") (release OR launched OR introduces OR "new tool")',
    topic_tags: list[str] | None = None,
) -> list[NewsItem]:
    """
    Fetch more candidates, score them (novelty/impact/clarity/tag match), diversify across tags,
    then return up to `limit` best items.
    """
    from .content_quality import diversify, load_seen_titles, save_seen_titles, score_item

    fetch_n = max(fetch_n, limit)
    # Fetch without seen-filter so novelty scoring can still pick the best; URL seen-filter is still applied below.
    raw = fetch_latest_items(limit=fetch_n, query=query, topic_tags=topic_tags)

    seen_titles_path = news_cache_dir / "seen_titles.json"
    seen_titles = load_seen_titles(seen_titles_path)

    # Source weights: can evolve later; keep simple now.
    source_weights = {"GoogleNews": 0.25, "MarkTechPost": 0.15}

    scored = []
    for it in raw:
        s = score_item(it, topic_tags=topic_tags, seen_titles=seen_titles, source_weights=source_weights)
        scored.append((s.total, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [it for _score, it in scored]
    diversified = diversify(ranked, topic_tags=topic_tags, k=max(1, int(limit)))

    # Maintain existing seen URL behavior (so repeated runs move forward).
    # Reuse get_latest_items filtering by feeding it through the existing seen mechanism:
    # we’ll manually filter URLs here and persist to seen.json.
    seen_path = news_cache_dir / "seen.json"
    seen = _load_seen(seen_path)
    out: list[NewsItem] = []
    for it in diversified:
        if it.url in seen:
            continue
        out.append(it)
        seen.add(it.url)
        if len(out) >= limit:
            break
    _save_seen(seen_path, seen)

    # Update seen titles list for novelty scoring next time
    try:
        for it in out:
            t = (it.title or "").strip()
            if t:
                seen_titles.append(t)
        save_seen_titles(seen_titles_path, seen_titles)
    except Exception:
        pass

    return out


def polite_sleep(min_s: float = 0.8, jitter_s: float = 0.6) -> None:
    time.sleep(min_s + (jitter_s * (time.time() % 1)))

