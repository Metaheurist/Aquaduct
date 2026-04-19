from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .topics import discover_uses_headline_sources, normalize_video_format, video_format_uses_news_style_sourcing

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
    # Optional preview image from Firecrawl search metadata (creative topic research).
    image_url: str | None = None


def news_item_to_script_source(item: NewsItem) -> dict[str, str]:
    """Fields passed to the script LLM (headlines JSON); includes recency when available."""
    pub = getattr(item, "published_at", None)
    out = {
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "published_at": (pub or "").strip(),
    }
    iu = (getattr(item, "image_url", None) or "").strip()
    if iu:
        out["image_url"] = iu
    return out


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
        # Topics → Discover: bias toward **animation / cartoon** comedy, not generic standup sketch or listicles.
        return (
            "(\"adult animation\" OR \"animated comedy\" OR cartoon OR \"animated short\" OR webcomic OR animatic OR "
            "\"2D animation\" OR \"cartoon parody\" OR \"animation meme\" OR \"funny cartoon\" OR \"visual comedy\") "
            "(meme OR absurdist OR surreal OR parody OR satire OR fandom OR \"character animation\" OR "
            "\"wholesome animation\" OR \"short animation\")"
        )
    if m == "unhinged":
        # Chaotic cartoon / meme culture — not generic “sketch comedy” SEO pages.
        return (
            "(unhinged OR absurd OR surreal OR brainrot OR \"cursed animation\" OR \"chaotic cartoon\" OR "
            "shitpost OR meme OR copypasta OR \"absurdist animation\" OR \"surreal meme\" OR liminal OR cursed OR "
            "\"internet humor\") "
            "(cartoon OR animation OR animated OR \"animated short\" OR parody OR satire OR meme OR comedy)"
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
        # News: topics only — headline fetch follows the user's tags (still deduped for freshness).
        # Explainer: keep tags + AI/product-release bias distinct from plain news.
        if mode == "news":
            return f"({tag_expr})"
        if mode == "explainer":
            return (
                f"({tag_expr}) (AI OR \"AI tool\" OR \"AI app\") "
                f"(release OR launched OR introduces OR \"new tool\")"
            )
        if mode == "cartoon":
            # Tags steer search; require animation/cartoon language so “sketch” alone doesn’t pull live standup SEO.
            return (
                f"({tag_expr}) "
                f"(cartoon OR animated OR animation OR webcomic OR \"adult animation\" OR \"animated comedy\" OR animatic) "
                f"(meme OR parody OR absurdist OR surreal OR satire OR \"short animation\" OR \"funny animation\")"
            )
        if mode == "unhinged":
            return (
                f"({tag_expr}) "
                f"(unhinged OR absurd OR surreal OR brainrot OR chaotic OR meme OR shitpost OR cursed OR liminal) "
                f"(cartoon OR animation OR animated OR parody OR satire OR \"animated short\" OR absurdist)"
            )
        return f"({tag_expr}) {_default_headline_query(mode)}"
    return _default_headline_query(mode)


def _extra_creative_firecrawl_queries(topic_mode: str | None, topic_tags: list[str] | None) -> list[str]:
    """Alternate search strings when the primary creative query under-fills (cartoon / unhinged only)."""
    m = _cache_mode_key(topic_mode)
    if m not in ("cartoon", "unhinged"):
        return []
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_prefix = ""
    if tags:
        tag_expr = " OR ".join(f'"{t}"' for t in tags[:8])
        tag_prefix = f"({tag_expr}) "
    if m == "cartoon":
        rest = [
            "(webcomic OR tapas OR webtoon OR newgrounds OR artstation) (cartoon OR animation OR comedy OR funny OR meme)",
            "(\"animated short\" OR animatic OR \"2D cartoon\" OR \"cartoon clip\") (comedy OR parody OR meme OR absurdist)",
            "(\"cartoon meme\" OR \"animation meme\" OR \"funny cartoon\" OR \"cursed cartoon\") (viral OR absurdist OR surreal)",
            "(\"character animation\" OR \"cartoon style\" OR illustration) (comedy OR humor OR satire) (animated OR cartoon)",
        ]
    else:
        rest = [
            "(\"absurdist animation\" OR \"surreal cartoon\" OR \"cursed cartoon\" OR unhinged) (meme OR viral OR comedy OR parody)",
            "(brainrot OR shitpost OR copypasta OR liminal) (cartoon OR animation OR meme OR absurd OR chaotic)",
            "(reddit OR tumblr) (\"animated meme\" OR \"cartoon clip\" OR \"funny animation\" OR absurdist OR surreal)",
            "(chaotic OR uncanny OR \"internet horror\" OR cursed) (animation OR cartoon OR meme OR comedy short)",
        ]
    return [f"{tag_prefix}{q}".strip() for q in rest]


def _fetch_headlines(
    *,
    limit: int,
    query: str,
    topic_tags: list[str] | None,
    topic_mode: str | None = "news",
    firecrawl_enabled: bool = False,
    firecrawl_api_key: str | None = None,
    timeout_s: int = 30,
    topic_discover_only: bool = False,
) -> list[NewsItem]:
    """Try Firecrawl search when enabled + key; then optional Google News RSS + MarkTechPost.

    For **news/explainer**, RSS/MarkTechPost run when Firecrawl under-fills.

    For **cartoon/unhinged**: extra Firecrawl meme-oriented queries run first. If still short,
    RSS + MarkTechPost run **unless** ``topic_discover_only`` is True (Topics tab **Discover** only),
    so preset runs / storyboard can still get URLs without Firecrawl.
    """
    q = _effective_query(query=query, topic_tags=topic_tags, topic_mode=topic_mode)
    fetched: list[NewsItem] = []
    key: str | None = None
    if firecrawl_enabled:
        try:
            from .firecrawl_news import firecrawl_search_news, resolve_firecrawl_api_key

            key = resolve_firecrawl_api_key(firecrawl_api_key)
        except Exception:
            key = None

    def _merge_firecrawl_raw(raw: list) -> None:
        have = {x.url for x in fetched}
        for d in raw:
            if not isinstance(d, dict):
                continue
            title = str(d.get("title") or "").strip()
            url = str(d.get("url") or "").strip()
            if not title or not url:
                continue
            if url in have:
                continue
            pub = d.get("published_at")
            pa = str(pub).strip() if pub else None
            img = d.get("image_url")
            iu = str(img).strip() if isinstance(img, str) and img.strip().startswith("http") else None
            fetched.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=str(d.get("source") or "Firecrawl"),
                    published_at=pa,
                    image_url=iu,
                )
            )
            have.add(url)

    if firecrawl_enabled and key:
        try:
            from .firecrawl_news import firecrawl_search_news

            raw = firecrawl_search_news(
                q,
                limit=limit,
                api_key=key,
                timeout_s=min(120, max(int(timeout_s), 25)),
            )
            _merge_firecrawl_raw(raw)
        except Exception:
            pass

    need = max(1, int(limit))
    use_headlines = discover_uses_headline_sources(topic_mode)

    if not use_headlines and firecrawl_enabled and key:
        try:
            from .firecrawl_news import firecrawl_search_news

            for q2 in _extra_creative_firecrawl_queries(topic_mode, topic_tags):
                if len(fetched) >= need:
                    break
                try:
                    raw2 = firecrawl_search_news(
                        q2,
                        limit=max(1, need - len(fetched)),
                        api_key=key,
                        timeout_s=min(120, max(int(timeout_s), 25)),
                    )
                    _merge_firecrawl_raw(raw2)
                except Exception:
                    continue
        except Exception:
            pass

    if use_headlines and len(fetched) < need:
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
    if use_headlines and len(fetched) < need:
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

    # Pipeline / runs / storyboard: cartoon & unhinged still get RSS+MarkTechPost if Firecrawl did not fill.
    # Topics → Discover passes topic_discover_only=True to keep headline RSS off for those modes.
    if (
        not use_headlines
        and len(fetched) < need
        and not topic_discover_only
    ):
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
    if (
        not use_headlines
        and len(fetched) < need
        and not topic_discover_only
    ):
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
        topic_discover_only=False,
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
    topic_discover_only: bool = False,
) -> list[NewsItem]:
    """
    Fetches up to `limit` items from sources WITHOUT applying the seen-cache filter.

    Set ``topic_discover_only=True`` only for the Topics tab **Discover** button (cartoon/unhinged skip
    headline RSS in that path). Pipeline and ``get_scored_items`` use the default ``False`` so runs
    can fall back to Google News RSS when Firecrawl returns nothing.
    """
    fetched = _fetch_headlines(
        limit=limit,
        query=query,
        topic_tags=topic_tags,
        topic_mode=topic_mode,
        firecrawl_enabled=firecrawl_enabled,
        firecrawl_api_key=firecrawl_api_key,
        topic_discover_only=topic_discover_only,
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

