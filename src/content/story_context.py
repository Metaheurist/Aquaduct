"""
Optional web digest + reference image download for the script pipeline (Firecrawl).

For **cartoon** and **unhinged**, search is biased toward memes / viral / templates. For **creepypasta**, toward
horror fiction / atmospheric references. For **health_advice**, toward wellness and health-education pages.
Extra Firecrawl supplement queries run for those modes so scraped pages
yield richer reference images for diffusion.
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
from src.content.topics import normalize_video_format
from debug import dprint

MAX_DIGEST_CHARS = 12_000
MAX_SCRAPE_CHARS_PER_PAGE = 6000
MAX_SEARCH_LIMIT = 6
MAX_PAGES_TO_SCRAPE = 2
MAX_PAGES_TO_SCRAPE_MEME_MODES = 4
MAX_REFERENCE_IMAGES = 3
MAX_REFERENCE_IMAGES_MEME_MODES = 5
MEME_SUPPLEMENT_LIMIT = 4
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


def _tag_and_title_parts(topic_tags: list[str], source_titles: list[str]) -> str:
    parts: list[str] = []
    for t in topic_tags[:6]:
        t = " ".join(str(t).split()).strip()
        if t:
            parts.append(t)
    for title in source_titles[:2]:
        tt = " ".join(str(title).split()).strip()
        if tt:
            parts.append(tt[:120])
    return " ".join(parts).strip()


def _search_query(topic_tags: list[str], source_titles: list[str], video_format: str | None = None) -> str:
    vf = normalize_video_format(video_format or "news")
    base = _tag_and_title_parts(topic_tags, source_titles)
    if vf == "cartoon":
        meme_bias = (
            "(meme OR viral OR trending OR reaction OR template OR funny OR pop culture OR "
            "fandom humor OR animation meme OR comic meme OR still image meme)"
        )
        if base:
            return _trim(f"{base} {meme_bias}", 240)
        return _trim(
            "trending memes OR new viral meme OR cartoon meme template OR funny animation meme OR reaction meme 2025",
            240,
        )
    if vf == "unhinged":
        meme_bias = (
            "(meme OR viral OR shitpost OR trending OR reaction OR copypasta OR brainrot OR "
            "\"internet culture\" OR TikTok meme OR Reddit meme OR ironic OR absurdist humor)"
        )
        if base:
            return _trim(f"{base} {meme_bias}", 240)
        return _trim(
            "newest viral memes OR trending Twitter meme OR chaotic meme OR absurdist shitpost OR brainrot 2025",
            240,
        )
    if vf == "creepypasta":
        horror_bias = (
            "(creepypasta OR horror fiction OR scary story OR nosleep OR urban legend OR paranormal OR "
            "unsettling short story OR liminal horror OR ghost story OR atmospheric dread)"
        )
        if base:
            return _trim(f"{base} {horror_bias}", 240)
        return _trim(
            "creepypasta atmospheric horror reference OR liminal space photography OR vintage horror illustration",
            240,
        )
    if vf == "health_advice":
        health_bias = (
            "(wellness OR \"healthy habits\" OR nutrition OR sleep OR exercise OR \"mental health\" OR "
            "\"public health\" OR prevention OR \"evidence based\" OR \"health education\") "
            "(tips OR overview OR explained OR guide OR infographic)"
        )
        if base:
            return _trim(f"{base} {health_bias}", 240)
        return _trim(
            "\"wellness tips\" OR \"healthy lifestyle\" OR \"sleep hygiene\" OR \"heart health\" OR diabetes prevention OR stress management OR mindfulness OR hydration OR stretching",
            240,
        )
    q = base
    return _trim(q, 240) or "breaking news today"


def _meme_supplement_searches(
    *,
    video_format: str,
    topic_tags: list[str],
    source_titles: list[str],
) -> list[str]:
    """Extra Firecrawl queries for creative video formats to pull richer reference pages."""
    vf = normalize_video_format(video_format)
    if vf not in ("cartoon", "unhinged", "creepypasta", "health_advice"):
        return []
    tags = [t.strip() for t in topic_tags if str(t).strip()][:4]
    tag_expr = " OR ".join(f'"{t}"' for t in tags)
    seed = _trim(_tag_and_title_parts(topic_tags, source_titles), 100)
    lead = f"{seed} " if seed else ""
    tag_prefix = f"({tag_expr}) " if tag_expr else ""
    if vf == "cartoon":
        return [
            _trim(
                f"{lead}{tag_prefix}"
                "(knowyourmeme OR meme template OR reaction meme still OR funny cartoon meme OR pop culture meme image)",
                240,
            ),
            _trim(
                "(trending meme OR viral cartoon OR animation meme OR comic meme OR meme redraw reference)",
                240,
            ),
        ]
    if vf == "creepypasta":
        return [
            _trim(
                f"{lead}{tag_prefix}"
                "(liminal space photography OR analog horror still OR foggy street at night OR abandoned building interior)",
                240,
            ),
            _trim(
                "(vintage horror illustration OR unsettling silhouette art OR moonlit forest OR empty hallway)",
                240,
            ),
        ]
    if vf == "health_advice":
        return [
            _trim(
                f"{lead}{tag_prefix}"
                "(\"healthy eating\" OR mediterranean diet OR fiber OR protein OR vitamins OR minerals OR hydration) "
                "(science OR benefits OR guide OR explained)",
                240,
            ),
            _trim(
                "(stress OR anxiety OR mindfulness OR meditation OR sleep OR burnout OR self-care) "
                "(coping OR strategies OR wellness OR mental health OR overview)",
                240,
            ),
        ]
    return [
        _trim(
            f"{lead}{tag_prefix}"
            "(reddit meme OR twitter viral OR shitpost OR ironic meme OR brainrot OR meme PNG reaction)",
            240,
        ),
        _trim(
            "(newest viral memes this week OR absurdist meme OR tiktok trend meme OR chaotic humor)",
            240,
        ),
    ]


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
    video_format: str = "news",
) -> tuple[str, list[Path], Path | None, str]:
    """
    Build optional web digest and download reference images.

    For ``video_format`` **cartoon**, **unhinged**, **creepypasta**, or **health_advice**, search queries bias toward
    meme/viral, horror-atmosphere, or wellness-education content; two supplement Firecrawl searches run; more pages are scraped and more reference
    images may be saved when ``want_refs`` is true.

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

    vf_norm = normalize_video_format(video_format or "news")
    rich_web_mode = vf_norm in ("cartoon", "unhinged", "creepypasta", "health_advice")
    max_scrape = MAX_PAGES_TO_SCRAPE_MEME_MODES if rich_web_mode else MAX_PAGES_TO_SCRAPE
    max_ref_save = MAX_REFERENCE_IMAGES_MEME_MODES if rich_web_mode else MAX_REFERENCE_IMAGES
    img_cap = 16 if rich_web_mode else 12

    if want_web and can_fc:
        q = _search_query(topic_tags, source_titles, video_format)
        hits: list[dict] = []
        seen_u: set[str] = set()

        def _merge_hits(raw: list | None) -> None:
            for h in raw or []:
                if not isinstance(h, dict):
                    continue
                u = str(h.get("url") or "").strip()
                if not u or u in seen_u:
                    continue
                seen_u.add(u)
                hits.append(h)

        try:
            raw0 = firecrawl_search_news(q, limit=MAX_SEARCH_LIMIT, api_key=api_key)  # type: ignore[arg-type]
            _merge_hits(raw0)
        except Exception as e:
            dprint("story_context", "search failed", str(e))

        supplement: list[str] = []
        if rich_web_mode:
            supplement = _meme_supplement_searches(
                video_format=vf_norm, topic_tags=topic_tags, source_titles=source_titles
            )
            for mq in supplement:
                try:
                    raw_s = firecrawl_search_news(
                        mq, limit=MEME_SUPPLEMENT_LIMIT, api_key=api_key  # type: ignore[arg-type]
                    )
                    _merge_hits(raw_s)
                except Exception as e:
                    dprint("story_context", "supplement search failed", mq[:60], str(e))

        digest_parts.append(f"## Search query\n{q}\n")
        if supplement:
            sup_heading = (
                "Horror / atmosphere supplement queries"
                if vf_norm == "creepypasta"
                else "Wellness / education supplement queries"
                if vf_norm == "health_advice"
                else "Meme / viral supplement queries"
            )
            digest_parts.append(f"\n## {sup_heading}\n")
            for mq in supplement:
                digest_parts.append(f"- {mq}\n")
        digest_parts.append("\n## Result links\n")
        for h in hits[:24]:
            if isinstance(h, dict):
                digest_parts.append(f"- **{h.get('title', '')}** — {h.get('url', '')}\n")

        scraped = 0
        for h in hits:
            if scraped >= max_scrape:
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
            all_urls.extend(extract_image_urls_from_markdown(md, cap=img_cap))
    elif want_web and not can_fc:
        dprint("story_context", "web context requested but Firecrawl unavailable")

    extra = (extra_markdown or "").strip()
    if extra and want_refs and not all_urls:
        all_urls.extend(extract_image_urls_from_markdown(extra, cap=img_cap))

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
            if n >= max_ref_save:
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
