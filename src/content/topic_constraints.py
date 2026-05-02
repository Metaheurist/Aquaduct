"""Topic tags as hard constraints + source-quality scoring (Phase 6).

The legacy script LLM prompt treated `topic_tags` as a soft *bias*
("Topic tags (bias hashtags and story angle)"), which let the model
drift onto adjacent subject matter — the
``Two_Sentenced_Horror_Stories`` run produced a script about
"Sketch Comedy Shows" because the cartoon prompt's bias text wasn't
strong enough to override the article body. Phase 6 promotes the tags
to **hard constraints** with optional per-tag notes, and adds a small
source-quality scoring helper so the topic picker can surface a badge
for the chosen URL.

The module is import-cheap (no torch / brain) so it can be reused from
prompt builders, the topics tab, and the auto picker.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


_LOWER_QUALITY_TLD_HINTS = (
    ".tk",
    ".ml",
    ".cf",
    ".gq",
    ".ga",
)

_HIGH_QUALITY_DOMAINS = frozenset(
    {
        # General reference / reputable
        "wikipedia.org",
        "bbc.com",
        "bbc.co.uk",
        "reuters.com",
        "apnews.com",
        "npr.org",
        "nature.com",
        "science.org",
        "nih.gov",
        "cdc.gov",
        "who.int",
        "scientificamerican.com",
        "smithsonianmag.com",
        "nationalgeographic.com",
        "newscientist.com",
        # Tech reference
        "github.com",
        "stackoverflow.com",
        "docs.python.org",
        "developer.mozilla.org",
        "kernel.org",
        "rfc-editor.org",
        # Wikis (story sources for creepypasta etc.)
        "creepypasta.fandom.com",
        "creepypasta.com",
        "scp-wiki.wikidot.com",
        "scp-wiki.net",
    }
)

_MID_QUALITY_DOMAINS = frozenset(
    {
        "fandom.com",
        "wikia.com",
        "medium.com",
        "substack.com",
        "dev.to",
        "hackernoon.com",
        "techcrunch.com",
        "theverge.com",
        "arstechnica.com",
        "wired.com",
        "engadget.com",
    }
)

_LOW_QUALITY_DOMAIN_FRAGMENTS = (
    "promo",
    "ad-network",
    "clickbait",
)


@dataclass(frozen=True)
class SourceQuality:
    """Heuristic quality assessment for a URL."""

    score: int  # 0..100
    badge: str  # "high" | "mid" | "low" | "unknown"
    reasons: tuple[str, ...]


def _normalize_tag(tag: str) -> str:
    return " ".join((tag or "").split()).strip().lower()


def normalize_tags(tags: Iterable[Any]) -> list[str]:
    """Lowercase + dedupe + drop empty tags while preserving input order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags or ():
        t = _normalize_tag(str(raw))
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def topic_notes_for(notes: Mapping[str, str] | None, tag: str) -> str:
    """Lookup the per-tag note (case-insensitive) and trim to a single line."""
    if not notes:
        return ""
    key = _normalize_tag(tag)
    for k, v in notes.items():
        if _normalize_tag(k) == key:
            txt = " ".join(str(v or "").split()).strip()
            return txt[:240]
    return ""


def topic_constraints_block(
    topic_tags: Iterable[str] | None,
    *,
    notes: Mapping[str, str] | None = None,
    cast_names: Iterable[str] | None = None,
) -> str:
    """Build a MUST-style block for the script LLM prompt.

    The block uses an ordered list of bullet rules so the model treats the
    tags as required anchors instead of optional bias. Per-tag notes (when
    set) appear as inline ``-> note`` clauses; cast names (when present)
    are surfaced so the LLM keeps narration in-character.

    Returns ``""`` when the tag list is empty, so callers can drop the
    block harmlessly.
    """
    tags = normalize_tags(topic_tags or [])
    if not tags:
        return ""
    lines: list[str] = ["## Topic constraints (HARD — every segment must respect these)"]
    for t in tags:
        note = topic_notes_for(notes, t)
        if note:
            lines.append(f"- `{t}` -> {note}")
        else:
            lines.append(f"- `{t}`")
    cast = [c for c in (cast_names or []) if str(c or "").strip()]
    if cast:
        cast_str = ", ".join(str(c).strip() for c in cast[:4])
        lines.append(
            f"- Cast: keep all narration in-character for: {cast_str}. "
            "Use these names verbatim; do not invent additional speakers."
        )
    lines.append("- If a constraint conflicts with the source URL, prefer the constraint and flag the conflict in the description.")
    lines.append("- Do not introduce off-topic celebrities, brands, or products.")
    return "\n".join(lines) + "\n"


def topic_constraints_json(
    topic_tags: Iterable[str] | None,
    *,
    notes: Mapping[str, str] | None = None,
) -> str:
    """JSON-encoded mirror of :func:`topic_constraints_block` for legacy prompts.

    Returns an empty string when no tags. Useful when an existing prompt
    already shows the tags via ``json.dumps(...)`` and we only want to
    enrich it with the per-tag notes.
    """
    tags = normalize_tags(topic_tags or [])
    if not tags:
        return ""
    payload: list[dict[str, str]] = []
    for t in tags:
        entry: dict[str, str] = {"tag": t}
        note = topic_notes_for(notes, t)
        if note:
            entry["note"] = note
        payload.append(entry)
    return json.dumps(payload, ensure_ascii=False)


def _hostname(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower().lstrip(".")
    except Exception:
        return ""


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def score_source_url(url: str | None, *, body_length: int | None = None) -> SourceQuality:
    """Heuristic source-quality score on a 0..100 scale.

    Inputs:
      - ``url``: the article URL.
      - ``body_length`` (optional): char count of the cleaned article text.
        Longer bodies pass a fact-density floor that pure URL heuristics
        can't see.

    Returns :class:`SourceQuality` with a ``badge`` suitable for direct UI
    rendering (``"high" / "mid" / "low" / "unknown"``).
    """
    host = _strip_www(_hostname(url))
    reasons: list[str] = []
    score = 50  # neutral baseline
    badge = "unknown"

    if not host:
        return SourceQuality(score=0, badge="unknown", reasons=("missing url",))

    if host in _HIGH_QUALITY_DOMAINS or any(host.endswith("." + d) for d in _HIGH_QUALITY_DOMAINS):
        score = max(score, 90)
        badge = "high"
        reasons.append("known reputable domain")
    elif host in _MID_QUALITY_DOMAINS or any(host.endswith("." + d) for d in _MID_QUALITY_DOMAINS):
        score = max(score, 70)
        badge = "mid"
        reasons.append("user-generated reputable platform")
    elif any(host.endswith(tld) for tld in _LOWER_QUALITY_TLD_HINTS):
        score = min(score, 25)
        badge = "low"
        reasons.append("free / disposable TLD")
    elif any(frag in host for frag in _LOW_QUALITY_DOMAIN_FRAGMENTS):
        score = min(score, 35)
        badge = "low"
        reasons.append("promo/ad-network heuristic match")

    if body_length is not None:
        if int(body_length) >= 4000:
            score += 5
            reasons.append(f"body ≥4k chars ({int(body_length):,})")
        elif int(body_length) <= 600:
            score = max(0, score - 10)
            reasons.append(f"body <600 chars ({int(body_length):,})")

    score = max(0, min(100, score))
    if badge == "unknown":
        if score >= 80:
            badge = "high"
        elif score >= 55:
            badge = "mid"
        else:
            badge = "low"

    return SourceQuality(score=score, badge=badge, reasons=tuple(reasons))


def source_quality_label(q: SourceQuality | None) -> str:
    """Short pill label for a quality assessment, safe for UI rendering."""
    if q is None:
        return "unknown"
    return f"{q.badge.upper()} ({q.score})"


_BAD_NOTE_CHARS = re.compile(r"[\x00-\x1f]")


def sanitize_topic_tag_notes(raw: Any) -> dict[str, str]:
    """Coerce a settings-dict value into a clean ``{tag_lower: note}`` mapping."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        tag = _normalize_tag(str(k or ""))
        note = _BAD_NOTE_CHARS.sub(" ", str(v or "")).strip()
        if not tag or not note:
            continue
        out[tag] = note[:240]
    return out
