from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from .crawler import NewsItem
from .topics import normalize_video_format

_OG_TIMEOUT_S = 12
_DL_TIMEOUT_S = 25
_MAX_OG_FETCHES = 6


def _url_fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:18]


def try_fetch_og_image_url(page_url: str, *, timeout_s: float = _OG_TIMEOUT_S) -> str | None:
    """Lightweight HTML fetch to read og:image / twitter:image (no Firecrawl scrape)."""
    u = (page_url or "").strip()
    if not u.startswith("http"):
        return None
    try:
        r = requests.get(
            u,
            timeout=timeout_s,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AquaductTopicResearch/1.0)"},
        )
        r.raise_for_status()
    except Exception:
        return None
    html = r.text or ""
    if len(html) < 80:
        return None
    soup = BeautifulSoup(html, "lxml")
    for prop in ("og:image", "twitter:image", "twitter:image:src"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            c = str(tag["content"]).strip()
            if c.startswith("http"):
                return c
    return None


def _guess_ext_from_content_type(ct: str | None) -> str:
    if not ct:
        return ".img"
    c = ct.lower()
    if "jpeg" in c or "jpg" in c:
        return ".jpg"
    if "png" in c:
        return ".png"
    if "webp" in c:
        return ".webp"
    if "gif" in c:
        return ".gif"
    return ".img"


def _download_image(image_url: str, dest: Path, *, timeout_s: float = _DL_TIMEOUT_S) -> Path | None:
    try:
        r = requests.get(
            image_url,
            timeout=timeout_s,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AquaductTopicResearch/1.0)"},
            stream=True,
        )
        r.raise_for_status()
        ext = _guess_ext_from_content_type(r.headers.get("Content-Type"))
        if dest.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".img"):
            dest = dest.with_suffix(ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        if dest.exists() and dest.stat().st_size > 80:
            return dest
    except Exception:
        try:
            if dest.exists():
                dest.unlink(missing_ok=True)
        except Exception:
            pass
    return None


def write_topic_research_pack(
    *,
    items: list[NewsItem],
    mode: str,
    data_dir: Path,
) -> Path | None:
    """
    Save a manifest plus downloaded preview images for Cartoon / Unhinged topic Discover.

    Images come from Firecrawl search ``image_url`` when present; otherwise we try ``og:image`` for the
    first few result pages (best-effort). Output is under ``data_dir / topic_research / {mode} /``.
    """
    m = (mode or "news").strip().lower()
    if m not in ("cartoon", "unhinged"):
        return None
    if not items:
        return None

    root = (data_dir / "topic_research" / m).resolve()
    img_dir = root / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    # Fresh run: remove previous images to avoid unbounded growth.
    for p in img_dir.glob("*"):
        try:
            if p.is_file():
                p.unlink()
        except Exception:
            pass

    entries: list[dict[str, Any]] = []
    og_budget = _MAX_OG_FETCHES

    for idx, it in enumerate(items):
        title = (it.title or "").strip()
        url = (it.url or "").strip()
        img_url = (getattr(it, "image_url", None) or "").strip()
        if not img_url and url.startswith("http") and og_budget > 0:
            og_budget -= 1
            img_url = try_fetch_og_image_url(url) or ""

        local_name: str | None = None
        if img_url.startswith("http"):
            base = re.sub(r"[^\w\-]+", "_", _url_fingerprint(url + str(idx)))[:48]
            dest = img_dir / f"{base}.img"
            saved = _download_image(img_url, dest)
            if saved is not None:
                local_name = str(saved.relative_to(root)).replace("\\", "/")

        entries.append(
            {
                "title": title,
                "url": url,
                "source": it.source,
                "image_url": img_url or None,
                "local_image": local_name,
            }
        )

    manifest = {
        "mode": m,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    root.mkdir(parents=True, exist_ok=True)
    man_path = root / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def topic_research_digest_for_script(data_dir: Path, video_format: str, *, max_chars: int = 8000) -> str:
    """
    Markdown block for the script LLM: latest Topics-tab Discover manifest (titles, URLs, local image paths).
    Only cartoon / unhinged; empty string if no manifest.
    """
    m = normalize_video_format(video_format or "news")
    if m not in ("cartoon", "unhinged"):
        return ""
    man_path = (Path(data_dir) / "topic_research" / m / "manifest.json").resolve()
    if not man_path.is_file():
        return ""
    try:
        data = json.loads(man_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return ""
    root = man_path.parent
    lines: list[str] = [
        "## Topics tab research (latest Discover)",
        "Tone, meme, and visual inspiration from pages you discovered; local paths are saved preview images.",
        "",
    ]
    for e in entries[:24]:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title") or "").strip()
        url = str(e.get("url") or "").strip()
        loc = e.get("local_image")
        head = f"- **{title}** — {url}" if title else f"- {url}"
        if isinstance(loc, str) and loc.strip():
            p = (root / loc).resolve()
            if p.is_file():
                head += f"\n  - Reference image file: {p}"
        lines.append(head)
    text = "\n".join(lines)
    return text[:max_chars] if len(text) > max_chars else text
