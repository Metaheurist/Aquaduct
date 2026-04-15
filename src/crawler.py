from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


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


def polite_sleep(min_s: float = 0.8, jitter_s: float = 0.6) -> None:
    time.sleep(min_s + (jitter_s * (time.time() % 1)))

