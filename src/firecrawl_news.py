from __future__ import annotations

import os
from typing import Any

import requests

FIRECRAWL_V2_SEARCH = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_V1_SCRAPE = "https://api.firecrawl.dev/v1/scrape"


def resolve_firecrawl_api_key(stored: str | None) -> str | None:
    """Prefer FIRECRAWL_API_KEY env, then non-empty saved UI key."""
    env = (os.environ.get("FIRECRAWL_API_KEY") or "").strip()
    if env:
        return env
    s = (stored or "").strip()
    return s if s else None


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def firecrawl_search_news(
    query: str,
    *,
    limit: int,
    api_key: str,
    timeout_s: int = 60,
) -> list[dict[str, Any]]:
    """
    Firecrawl v2 search → list of dicts with title, url, source, published_at (for NewsItem).
    """
    q = (query or "").strip()
    if not q:
        return []
    body: dict[str, Any] = {
        "query": q,
        "limit": max(1, min(100, int(limit))),
        "country": "US",
    }
    r = requests.post(
        FIRECRAWL_V2_SEARCH,
        headers=_headers(api_key),
        json=body,
        timeout=timeout_s,
    )
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, dict) or not payload.get("success"):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows: list[dict[str, Any]] = []
    web = data.get("web")
    if isinstance(web, list) and web:
        rows = [x for x in web if isinstance(x, dict)]
    else:
        news = data.get("news")
        if isinstance(news, list):
            rows = [x for x in news if isinstance(x, dict)]
    out: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or row.get("snippet") or "").strip()
        url = str(row.get("url") or "").strip()
        if not title or not url:
            continue
        pub = row.get("date")
        published_at = str(pub).strip() if pub else None
        out.append(
            {
                "title": title,
                "url": url,
                "source": "Firecrawl",
                "published_at": published_at,
            }
        )
        if len(out) >= limit:
            break
    return out


def firecrawl_scrape_markdown(url: str, *, api_key: str, timeout_s: int = 60) -> str:
    """
    Scrape a single URL via Firecrawl v1; return markdown (or best-effort text).
    """
    u = (url or "").strip()
    if not u:
        return ""
    body = {"url": u, "formats": ["markdown"]}
    r = requests.post(
        FIRECRAWL_V1_SCRAPE,
        headers=_headers(api_key),
        json=body,
        timeout=timeout_s,
    )
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, dict) or not payload.get("success"):
        return ""
    data = payload.get("data")
    if not isinstance(data, dict):
        return ""
    md = data.get("markdown")
    if isinstance(md, str) and md.strip():
        text = md.strip()
        return text[:10000]
    html = data.get("html")
    if isinstance(html, str) and html.strip():
        return " ".join(html.split()).strip()[:10000]
    return ""
