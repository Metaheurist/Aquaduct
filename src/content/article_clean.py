"""Sanitize raw article excerpts before they reach the script LLM.

Why
---
``fetch_article_text`` in :mod:`src.content.crawler` decomposes the obvious
``<header>``, ``<footer>``, ``<nav>``, ``<aside>``, ``<script>``, ``<style>``,
and ``<noscript>`` blocks, then concatenates the longest text candidate. On
Fandom / Wikipedia / community wikis, the longest candidate still includes
significant rail chrome:

* "Fan Feed", "Trending pages", "Popular pages", "More Stories", "More
  Categories" rails near the end of the page.
* Numbered "1 X", "2 Y", "3 Z" link lists from category indexes.
* Cookie / consent banners that survived the soup pruning.
* Site-wide breadcrumbs ("Aquaduct Wiki / Stories / ...").
* "Categories: A B C D" footer rows.
* "Edit this article", "Talk", "View source", reference superscripts
  (``[1]``, ``[citation needed]``, ``[2]``).

Pre-Phase-3 the LLM saw all of that as "story content", which produced
generic openings like *"Fan feed: trending pages — top horror stories on
Fandom"* instead of the actual two-sentence horror premise.

This module sits **before** the chunked LLM relevance pass added in
Phase 10: it is a deterministic regex-based cleaner so even when the
relevance pass is disabled or the LLM is unavailable, the script prompt
sees a tighter excerpt than the raw page text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse


# Lowercase substrings that mark the start of a wiki/Fandom rail block. We
# keep the cleaner conservative: each pattern is anchored to a recognizable
# rail header so regular paragraphs that happen to mention these phrases
# survive.
_FANDOM_RAIL_HEADERS: tuple[str, ...] = (
    "fan feed",
    "trending pages",
    "popular pages",
    "more stories",
    "more pages",
    "more categories",
    "categories list",
    "see more from this wiki",
    "explore properties",
    "follow us",
    "advertise",
    "media kit",
    "contact us",
    "terms of use",
    "privacy policy",
    "cookie settings",
    "manage cookie preferences",
    "do not sell or share my personal information",
    "support fandom",
    "fandom apps",
    "report this ad",
    "edit this article",
    "view source",
    "view history",
    "discuss this article",
    "what links here",
    "related changes",
    "special pages",
    "printable version",
    "permanent link",
    "page information",
    "cite this page",
)

# Citation / footnote markers like "[1]", "[12]", "[citation needed]".
_CITATION_RE = re.compile(r"\[(?:\d{1,3}|citation needed|cn|note|edit|update|when\?|who\?)\]", re.IGNORECASE)

# Numbered list openers used by Fandom "Trending pages" rails: lines that
# look like "1 Title 2 Other title 3 ...". We collapse runs of these.
_NUMBERED_LIST_RE = re.compile(r"\b(\d{1,2})\s+([A-Z][\w'’\- ]{0,80}?)(?=\s+\d{1,2}\s+[A-Z]|$)")

# "Categories: A B C D ..." trailers (Wikipedia / Fandom).
_CATEGORIES_TAIL_RE = re.compile(r"\bCategories?\s*:\s*[\w \-,’'/&()]+$", re.IGNORECASE)

# Generic "share / follow / subscribe" cookie / promo lines.
_PROMO_LINE_RE = re.compile(
    r"\b(share this|follow on|subscribe to|sign up for|click here to|cookie consent|"
    r"accept all cookies|read more on|related articles?|recommended for you)\b",
    re.IGNORECASE,
)

# Wiki edit chrome: "Edit", "Talk", "Read", "View source" navigation tabs.
_NAV_TABS_RE = re.compile(r"\b(Edit|Talk|Read|View source|View history|Watch)\b\s*\|\s*", re.IGNORECASE)

# "Page X of Y" pagers.
_PAGER_RE = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.IGNORECASE)


def _cut_at_rail(text: str) -> str:
    """Truncate ``text`` at the first rail-header substring we recognize."""
    if not text:
        return ""
    low = text.lower()
    cut_at: int | None = None
    for pat in _FANDOM_RAIL_HEADERS:
        idx = low.find(pat)
        if idx == -1:
            continue
        if cut_at is None or idx < cut_at:
            cut_at = idx
    return text if cut_at is None else text[:cut_at]


def _strip_lines_with_promo(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines():
        if _PROMO_LINE_RE.search(line) and len(line) <= 200:
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _collapse_numbered_lists(text: str) -> str:
    """Replace dense '1 X 2 Y 3 Z ...' link rails with a single 'related: X, Y, Z' note."""
    matches = list(_NUMBERED_LIST_RE.finditer(text))
    if len(matches) < 4:
        return text
    titles = [m.group(2).strip() for m in matches if m.group(2).strip()]
    if not titles:
        return text
    span_start = matches[0].start()
    span_end = matches[-1].end()
    chunk = text[span_start:span_end]
    if len(matches) >= 4 and len(chunk) > 60:
        replacement = f"(related pages: {', '.join(titles[:6])}…)"
        text = text[:span_start] + replacement + text[span_end:]
    return text


def _domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _is_wiki_like(url: str | None) -> bool:
    d = _domain(url)
    if not d:
        return False
    return ".fandom.com" in d or "wikipedia.org" in d.split(".") or "wiki" in d


def clean_article_excerpt(
    text: str,
    *,
    url: str | None = None,
    max_chars: int = 8000,
    aggressive: bool | None = None,
) -> str:
    """Return a tightened article excerpt suitable for prompts.

    Parameters
    ----------
    text:
        Raw text from :func:`src.content.crawler.fetch_article_text` or
        equivalent (already mostly tag-stripped).
    url:
        Original page URL; controls aggressive wiki/Fandom rules.
    max_chars:
        Hard cap on the returned excerpt size (mirrors the existing 10 000
        char cap in :func:`fetch_article_text`, but defaults tighter).
    aggressive:
        Force aggressive wiki cleaning. ``None`` (default) auto-enables it
        for Fandom / Wikipedia / `*wiki*` URLs.
    """
    if not text:
        return ""

    aggro = bool(aggressive) if aggressive is not None else _is_wiki_like(url)

    # 1. Drop citation / superscript markers.
    cleaned = _CITATION_RE.sub("", text)

    # 2. Strip nav tabs and pagers.
    cleaned = _NAV_TABS_RE.sub("", cleaned)
    cleaned = _PAGER_RE.sub("", cleaned)

    # 3. On wiki-like sources, cut at the first known rail and collapse the
    #    numbered "Trending pages" lists.
    if aggro:
        cleaned = _cut_at_rail(cleaned)
        cleaned = _collapse_numbered_lists(cleaned)
        cleaned = _CATEGORIES_TAIL_RE.sub("", cleaned)
    else:
        # Even on regular news pages, collapse runs of numbered links.
        cleaned = _collapse_numbered_lists(cleaned)

    # 4. Drop common share/follow/cookie promo lines.
    cleaned = _strip_lines_with_promo(cleaned)

    # 5. Normalize whitespace.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    # 6. Cap size.
    if len(cleaned) > max_chars:
        cut = cleaned.rfind(" ", 0, max_chars - 1)
        cleaned = cleaned[: cut if cut > 0 else max_chars - 1] + "…"
    return cleaned


def clean_many(
    items: Iterable[tuple[str | None, str]], *, max_chars: int = 8000
) -> list[str]:
    """Clean a batch of (url, text) pairs."""
    return [clean_article_excerpt(t, url=u, max_chars=max_chars) for (u, t) in items]
