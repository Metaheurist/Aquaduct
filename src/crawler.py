from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .topics import normalize_video_format, video_format_uses_news_style_sourcing

# Per `video_format`: separate seen URL + seen-title history so e.g. cartoon runs
# do not consume the same "fresh URL" budget as news (legacy flat files map to `news`).


def _cache_mode_key(mode: str | None) -> str:
    return normalize_video_format(mode or "news")


def news_seen_paths(news_cache_dir: Path, mode: str | None) -> tuple[Path, Path]:
    """Paths for `seen_<mode>.json` and `seen_titles_<mode>.json` under `news_cache_dir`."""
    m = _cache_mode_key(mode)
    return (
        news_cache_dir / f"seen_{m}.json",
        news_cache_dir / f"seen_titles_{m}.json",
    )


def clear_news_seen_cache_files(news_cache_dir: Path) -> int:
    """
    Remove legacy flat `seen.json` / `seen_titles.json` and all per-mode `seen_*.json` /
    `seen_titles_*.json` files. Returns how many files were deleted.
    """
    removed = 0
    for name in ("seen.json", "seen_titles.json"):
        p = news_cache_dir / name
        if p.exists():
            p.unlink()
            removed += 1
    for pattern in ("seen_*.json", "seen_titles_*.json"):
        for p in news_cache_dir.glob(pattern):
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
    return removed


def _load_seen_migrated(news_cache_dir: Path, mode: str | None) -> tuple[Path, set[str]]:
    """Load seen URL set; for `news`, fall back to legacy `seen.json` if per-mode file missing."""
    path, _ = news_seen_paths(news_cache_dir, mode)
    seen = _load_seen(path)
    if seen:
        return path, seen
    if _cache_mode_key(mode) == "news":
        legacy = news_cache_dir / "seen.json"
        return path, _load_seen(legacy)
    return path, set()


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


def _default_headline_query(mode: str | None) -> str:
    """RSS/search baseline when there are no user topic tags (per video format)."""
    m = _cache_mode_key(mode)
    # News + Explainer: same AI/product headline sourcing (not separate "tutorial science" track).
    if video_format_uses_news_style_sourcing(m):
        return '("AI tool" OR "AI agent" OR "AI app") (release OR launched OR introduces OR "new tool")'
    if m == "cartoon":
        # Newest animation / cartoon industry stories — entertainment buzz, not how-to tutorials.
        return (
            "(animation OR cartoon OR anime OR \"animated series\" OR \"streaming\") "
            "(premiere OR trailer OR \"new season\" OR episode OR release OR Netflix OR Disney OR "
            "renewal OR cancelled OR review OR news OR buzz)"
        )
    if m == "unhinged":
        # Internet culture / trends as headline seeds (then the script satirizes in cartoon voice).
        return (
            "(viral OR meme OR trending OR TikTok OR \"internet culture\" OR Twitter OR Reddit OR "
            "challenge OR discourse OR drama OR \"pop culture\" OR influencer) "
            "(comedy OR satire OR parody OR absurd OR short OR clip OR animation OR cartoon)"
        )
    return '("AI tool" OR "AI agent" OR "AI app") (release OR launched OR introduces OR "new tool")'


def _effective_query(
    *,
    query: str,
    topic_tags: list[str] | None,
    topic_mode: str | None = "news",
) -> str:
    """
    Build a Google News / Firecrawl search string. Tags + mode pick different bias:
    news + explainer → AI/product releases (shared); cartoon → newest animation/cartoon buzz; unhinged → viral / internet-culture.
    """
    mode = _cache_mode_key(topic_mode)
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    if tags:
        tag_expr = " OR ".join(f'"{t}"' for t in tags[:12])
        if video_format_uses_news_style_sourcing(mode):
            return (
                f"({tag_expr}) (AI OR \"AI tool\" OR \"AI app\") "
                f"(release OR launched OR introduces OR \"new tool\")"
            )
        if mode == "cartoon":
            return (
                f"({tag_expr}) (animation OR cartoon OR anime OR series OR streaming) "
                f"(premiere OR trailer OR episode OR season OR release OR review OR news OR buzz)"
            )
        if mode == "unhinged":
            return (
                f"({tag_expr}) (viral OR meme OR trending OR \"internet culture\" OR TikTok OR comedy OR "
                f"satire OR parody OR animation OR short OR discourse OR drama)"
            )
        return f"({tag_expr}) {_default_headline_query(mode)}"
    return _default_headline_query(mode)


def _fetch_headlines(
    *,
    limit: int,
    query: str,
    topic_tags: list[str] | None,
    topic_mode: str | None = "news",
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
    timeout_s: int = 30,
) -> list[NewsItem]:
    """Try Firecrawl search when enabled + key; then Google News RSS; then MarkTechPost."""
    q = _effective_query(query=query, topic_tags=topic_tags, topic_mode=topic_mode)
    fetched: list[NewsItem] = []
    key: str | None = None
    if firecrawl_enabled:
        try:
            from .firecrawl_news import firecrawl_search_news, resolve_firecrawl_api_key

            key = resolve_firecrawl_api_key(firecrawl_api_key)
        except Exception:
            key = None
    if firecrawl_enabled and key:
        try:
            raw = firecrawl_search_news(
                q,
                limit=limit,
                api_key=key,
                timeout_s=min(120, max(int(timeout_s), 25)),
            )
            for d in raw:
                if not isinstance(d, dict):
                    continue
                title = str(d.get("title") or "").strip()
                url = str(d.get("url") or "").strip()
                if not title or not url:
                    continue
                pub = d.get("published_at")
                pa = str(pub).strip() if pub else None
                fetched.append(
                    NewsItem(
                        title=title,
                        url=url,
                        source=str(d.get("source") or "Firecrawl"),
                        published_at=pa,
                    )
                )
        except Exception:
            pass

    need = max(1, int(limit))
    if len(fetched) < need:
        try:
            more = _google_news_rss(query=q, limit=need, timeout_s=timeout_s)
        except Exception:
            more = []
        have = {x.url for x in fetched}
        for it in more:
            if it.url in have:
                continue
            fetched.append(it)
            have.add(it.url)
            if len(fetched) >= need:
                break
    if len(fetched) < need:
        try:
            more = _marktechpost_latest(limit=need - len(fetched), timeout_s=timeout_s)
        except Exception:
            more = []
        have = {x.url for x in fetched}
        for it in more:
            if it.url in have:
                continue
            fetched.append(it)
            have.add(it.url)
            if len(fetched) >= need:
                break

    return fetched[:need]


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
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
    cache_mode: str | None = "news",
) -> list[NewsItem]:
    """
    Returns up to `limit` fresh items not seen before.
    Dedupes by URL and persists per-mode `seen_<mode>.json` (legacy `seen.json` seeds `news` only).
    """
    seen_path, seen = _load_seen_migrated(news_cache_dir, cache_mode)

    fetched = _fetch_headlines(
        limit=limit,
        query=query,
        topic_tags=topic_tags,
        topic_mode=cache_mode,
        firecrawl_enabled=firecrawl_enabled,
        firecrawl_api_key=firecrawl_api_key,
    )

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
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
    topic_mode: str | None = "news",
) -> list[NewsItem]:
    """
    Fetches up to `limit` items from sources WITHOUT applying the seen-cache filter.
    Use this for UI discovery features where "newest headlines" matters more than "unseen".
    """
    fetched = _fetch_headlines(
        limit=limit,
        query=query,
        topic_tags=topic_tags,
        topic_mode=topic_mode,
        firecrawl_enabled=firecrawl_enabled,
        firecrawl_api_key=firecrawl_api_key,
    )

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


def fetch_article_text(
    url: str,
    *,
    timeout_s: int = 35,
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
) -> str:
    """
    Best-effort article text extraction from a URL.
    Intended for lightweight verification/summary; not perfect.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if firecrawl_enabled:
        try:
            from .firecrawl_news import firecrawl_scrape_markdown, resolve_firecrawl_api_key

            k = resolve_firecrawl_api_key(firecrawl_api_key)
            if k:
                text = firecrawl_scrape_markdown(url, api_key=k, timeout_s=min(120, max(int(timeout_s), 20)))
                if text.strip():
                    return text[:10000]
        except Exception:
            pass
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
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
    cache_mode: str | None = "news",
    persist_cache: bool = True,
) -> list[NewsItem]:
    """
    Fetch more candidates, score them (novelty/impact/clarity/tag match), diversify across tags,
    then return up to `limit` best items.

    When ``persist_cache`` is False, URL/title history under ``news_cache_dir`` is not read or
    written (used for Cartoon unhinged preset runs).
    """
    from .content_quality import diversify, load_seen_titles, save_seen_titles, score_item

    fetch_n = max(fetch_n, limit)
    # Fetch without seen-filter so novelty scoring can still pick the best; URL seen-filter is still applied below.
    raw = fetch_latest_items(
        limit=fetch_n,
        query=query,
        topic_tags=topic_tags,
        firecrawl_enabled=firecrawl_enabled,
        firecrawl_api_key=firecrawl_api_key,
        topic_mode=cache_mode,
    )

    _, seen_titles_path = news_seen_paths(news_cache_dir, cache_mode)
    if persist_cache:
        seen_titles = load_seen_titles(seen_titles_path)
        if not seen_titles and _cache_mode_key(cache_mode) == "news":
            seen_titles = load_seen_titles(news_cache_dir / "seen_titles.json")
    else:
        seen_titles = []

    # Source weights: can evolve later; keep simple now.
    source_weights = {"GoogleNews": 0.25, "MarkTechPost": 0.15, "Firecrawl": 0.25}

    scored = []
    for it in raw:
        s = score_item(it, topic_tags=topic_tags, seen_titles=seen_titles, source_weights=source_weights)
        scored.append((s.total, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [it for _score, it in scored]
    diversified = diversify(ranked, topic_tags=topic_tags, k=max(1, int(limit)))

    # Maintain existing seen URL behavior (so repeated runs move forward).
    # Reuse get_latest_items filtering by feeding it through the existing seen mechanism:
    # we’ll manually filter URLs here and persist to seen_<mode>.json.
    out: list[NewsItem] = []
    if persist_cache:
        seen_path, seen = _load_seen_migrated(news_cache_dir, cache_mode)
        for it in diversified:
            if it.url in seen:
                continue
            out.append(it)
            seen.add(it.url)
            if len(out) >= limit:
                break
        _save_seen(seen_path, seen)
    else:
        seen_urls: set[str] = set()
        for it in diversified:
            if it.url in seen_urls:
                continue
            out.append(it)
            seen_urls.add(it.url)
            if len(out) >= limit:
                break

    # Update seen titles list for novelty scoring next time
    if persist_cache:
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

