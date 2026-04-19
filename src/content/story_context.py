"""
Optional web digest + reference image download for the script pipeline (Firecrawl).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
import requests
from PIL import Image

from src.content.firecrawl_news import (
    firecrawl_scrape_markdown,
    firecrawl_search_news,
    resolve_firecrawl_api_key,
)
from debug import dprint

MAX_DIGEST_CHARS = 12_000
MAX_SCRAPE_CHARS_PER_PAGE = 6000
MAX_SEARCH_LIMIT = 6
MAX_PAGES_TO_SCRAPE = 2
MAX_REFERENCE_IMAGES = 3
MAX_IMAGE_BYTES = 2_000_000
IMAGE_DOWNLOAD_TIMEOUT_S = 35

_MD_IMG = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_HTML_IMG = re.compile(r"""<img[^>]+src=["'](https?://[^"']+)["']""", re.IGNORECASE)


def _trim(s: str, cap: int) -> str:
    t = (s or "").strip()
    return t if len(t) <= cap else t[: cap - 1] + "…"


def extract_image_urls_from_markdown(md: str, cap: int = 20) -> list[tuple[str, str]]:
    """Return (alt_text, url) pairs from markdown / loose HTML in scraped text."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _MD_IMG.finditer(md or ""):
        alt, url = m.group(1).strip(), m.group(2).strip()
        if url not in seen:
            seen.add(url)
            out.append((alt, url))
        if len(out) >= cap:
            break
    if len(out) < cap:
        for m in _HTML_IMG.finditer(md or ""):
            url = m.group(1).strip()
            if url not in seen:
                seen.add(url)
                out.append(("", url))
            if len(out) >= cap:
                break
    return out


def _search_query(topic_tags: list[str], source_titles: list[str]) -> str:
    parts: list[str] = []
    for t in topic_tags[:6]:
        t = " ".join(str(t).split()).strip()
        if t:
            parts.append(t)
    for title in source_titles[:2]:
        tt = " ".join(str(title).split()).strip()
        if tt:
            parts.append(tt[:120])
    q = " ".join(parts).strip()
    return _trim(q, 240) or "breaking news today"


def _download_one_image(url: str, dest: Path) -> bool:
    try:
        r = requests.get(
            url,
            timeout=IMAGE_DOWNLOAD_TIMEOUT_S,
            stream=True,
            headers={"User-Agent": "AquaductStoryContext/1.0"},
        )
        r.raise_for_status()
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
            return False
        buf = io.BytesIO()
        n = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            n += len(chunk)
            if n > MAX_IMAGE_BYTES:
                return False
            buf.write(chunk)
        buf.seek(0)
        im = Image.open(buf).convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, format="PNG")
        return True
    except Exception as e:
        dprint("story_context", "image download failed", url[:80], str(e))
        return False


def build_script_context(
    *,
    topic_tags: list[str],
    source_titles: list[str],
    stored_firecrawl_key: str,
    firecrawl_enabled: bool,
    want_web: bool,
    want_refs: bool,
    out_dir: Path,
    extra_markdown: str = "",
) -> tuple[str, list[Path], Path | None, str]:
    """
    Build optional web digest and download reference images.

    Returns:
        digest_text (trimmed, for LLM),
        list of saved reference image paths,
        primary reference path (first image) for diffusion, or None,
        reference_notes string (filenames + alt hints for prompts).
    """
    out_dir = Path(out_dir)
    ctx_dir = out_dir / "script_context"
    ref_dir = ctx_dir / "references"
    digest_parts: list[str] = []
    all_urls: list[tuple[str, str]] = []

    api_key = resolve_firecrawl_api_key(stored_firecrawl_key if firecrawl_enabled else None)
    can_fc = bool(api_key) and bool(firecrawl_enabled)

    if want_web and can_fc:
        q = _search_query(topic_tags, source_titles)
        try:
            hits = firecrawl_search_news(q, limit=MAX_SEARCH_LIMIT, api_key=api_key)  # type: ignore[arg-type]
        except Exception as e:
            dprint("story_context", "search failed", str(e))
            hits = []
        digest_parts.append(f"## Search query\n{q}\n")
        for h in hits[:MAX_SEARCH_LIMIT]:
            if isinstance(h, dict):
                digest_parts.append(
                    f"- **{h.get('title', '')}** — {h.get('url', '')}\n"
                )
        scraped = 0
        for h in hits:
            if scraped >= MAX_PAGES_TO_SCRAPE:
                break
            u = str(h.get("url") or "").strip() if isinstance(h, dict) else ""
            if not u:
                continue
            try:
                md = firecrawl_scrape_markdown(u, api_key=api_key, timeout_s=60)
            except Exception as e:
                dprint("story_context", "scrape failed", u[:60], str(e))
                continue
            scraped += 1
            digest_parts.append(f"\n## Source\n{u}\n\n{_trim(md, MAX_SCRAPE_CHARS_PER_PAGE)}\n")
            all_urls.extend(extract_image_urls_from_markdown(md, cap=12))
    elif want_web and not can_fc:
        dprint("story_context", "web context requested but Firecrawl unavailable")

    extra = (extra_markdown or "").strip()
    if extra and want_refs and not all_urls:
        all_urls.extend(extract_image_urls_from_markdown(extra, cap=12))

    digest = _trim("\n".join(digest_parts), MAX_DIGEST_CHARS)
    if digest.strip():
        try:
            ctx_dir.mkdir(parents=True, exist_ok=True)
            (ctx_dir / "web_digest.md").write_text(digest, encoding="utf-8")
        except OSError:
            pass

    ref_paths: list[Path] = []
    primary: Path | None = None
    alts: list[str] = []

    if want_refs:
        # Prefer images discovered during scrape; URLs only (skip data:)
        n = 0
        for alt, url in all_urls:
            if n >= MAX_REFERENCE_IMAGES:
                break
            if not url.startswith("http"):
                continue
            dest = ref_dir / f"ref_{n:02d}.png"
            if _download_one_image(url, dest):
                ref_paths.append(dest)
                if alt:
                    alts.append(alt[:120])
                n += 1
        if ref_paths:
            primary = ref_paths[0]

    notes_lines = [f"Saved reference: {p.name}" for p in ref_paths]
    if alts:
        notes_lines.append("Image alt hints from pages: " + "; ".join(alts[:5]))
    reference_notes = "\n".join(notes_lines) if notes_lines else ""

    return digest, ref_paths, primary, reference_notes
