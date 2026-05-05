"""Video package parsing, arc enforcement, custom-mode fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.core.config import ARTICLE_EXCERPT_MAX_CHARS, BrandingSettings
from src.util.llm_json_extract import parse_first_json_dict_from_llm_text

from ..personalities import get_personality_by_id

def clip_article_excerpt(text: str | None, *, max_chars: int | None = None) -> str:
    """Trim article body for LLM prompts; empty if no text."""
    cap = max_chars if max_chars is not None else ARTICLE_EXCERPT_MAX_CHARS
    t = (text or "").strip()
    if not t:
        return ""
    return t[:cap]

@dataclass(frozen=True)
class ScriptSegment:
    narration: str
    visual_prompt: str
    on_screen_text: str | None = None


@dataclass(frozen=True)
class VideoPackage:
    title: str
    description: str
    hashtags: list[str]
    hook: str
    segments: list[ScriptSegment]
    cta: str

    def narration_text(self) -> str:
        parts: list[str] = []
        if self.hook.strip():
            parts.append(self.hook.strip())
        parts.extend(s.narration.strip() for s in self.segments if s.narration.strip())
        if self.cta.strip():
            parts.append(self.cta.strip())
        return " ".join(parts).strip()


def _extract_json(text: str) -> dict[str, Any]:
    """
    Best-effort JSON extraction from a model response that may include prose.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("No JSON object found in model output.")
    parsed = parse_first_json_dict_from_llm_text(raw)
    if parsed is None:
        raise ValueError("No JSON object found in model output.")
    return parsed


def _normalize_hashtags(tags: list[Any]) -> list[str]:
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        # Keep TikTok-friendly tags short-ish
        t = re.sub(r"\s+", "", t)
        if 2 <= len(t) <= 40:
            out.append(t)
    # de-dupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped[:30]


def _synthesize_visual_prompt(
    *,
    narration: str,
    on_screen_text: str | None,
    title: str,
    video_format: str = "",
) -> str:
    """Build a usable ``visual_prompt`` from narration when the LLM omitted one.

    Pre-Phase-3 behavior: ``_to_package`` silently dropped any segment without
    *both* ``narration`` and ``visual_prompt``. On the
    ``Two_Sentenced_Horror_Stories`` run that quietly lost most beats, leaving
    the storyboard with a single placeholder scene which the T2V model then
    repeated. Synthesizing here keeps the script intact and lets the
    scene-prompt builder enrich it later (Phase 4).
    """
    base = (narration or "").strip()
    cap = 220
    if len(base) > cap:
        base = base[:cap].rsplit(" ", 1)[0] + "…"
    bits: list[str] = []
    vf = (video_format or "").strip().lower()
    if vf == "creepypasta":
        bits.append("cinematic vertical 9:16 horror still, dim moody lighting, atmospheric dread")
    elif vf == "cartoon":
        bits.append("expressive 9:16 cartoon scene, bold linework, dynamic composition")
    elif vf == "unhinged":
        bits.append("vivid 9:16 satirical animation still, exaggerated character expressions")
    elif vf == "health_advice":
        bits.append("clean vertical 9:16 explainer scene, friendly clear infographic feel")
    elif vf == "nsfw":
        bits.append("cinematic vertical 9:16 soft studio light, tasteful adult editorial portrait mood, consenting adult talent")
    elif vf == "news":
        bits.append("vertical 9:16 news-style frame, sharp focus, clear subject framing")
    elif vf == "explainer":
        bits.append("vertical 9:16 explainer frame, clean composition, readable subject")
    else:
        bits.append("vertical 9:16 short video frame, cinematic composition")
    if base:
        bits.append(f"depicting: {base}")
    if on_screen_text:
        cap2 = 80
        ost = on_screen_text.strip()
        if ost:
            bits.append(f"in-scene text/title cue: \"{ost[:cap2]}\"")
    if title and not base.lower().startswith(title.lower()[:10]):
        tcap = title.strip()[:80]
        if tcap:
            bits.append(f"thematic anchor: {tcap}")
    return ", ".join(b for b in bits if b)


def _synthesize_narration_from_visual(visual: str) -> str:
    v = (visual or "").strip()
    if not v:
        return ""
    if len(v) > 240:
        v = v[:240].rsplit(" ", 1)[0] + "…"
    return v


def _to_package(data: dict[str, Any], *, video_format: str = "") -> VideoPackage:
    title = str(data.get("title", "")).strip() or "Short video"
    description = str(data.get("description", "")).strip()
    if not description:
        description = "A fast vertical short driven by the topics and sources you picked."

    hashtags = _normalize_hashtags(data.get("hashtags", []) if isinstance(data.get("hashtags"), list) else [])
    if not hashtags:
        hashtags = ["#Shorts", "#Video", "#Story", "#Vertical", "#Watch"]

    hook = str(data.get("hook", "")).strip()
    cta = str(data.get("cta", "")).strip() or "Follow for more shorts like this."

    segs_raw = data.get("segments", [])
    segments: list[ScriptSegment] = []
    if isinstance(segs_raw, list):
        for s in segs_raw:
            if not isinstance(s, dict):
                continue
            narration = str(s.get("narration", "")).strip()
            visual = str(s.get("visual_prompt", "")).strip()
            on_screen = s.get("on_screen_text", None)
            on_screen_text = str(on_screen).strip() if isinstance(on_screen, str) and on_screen.strip() else None
            if not narration and not visual:
                continue
            if not visual:
                visual = _synthesize_visual_prompt(
                    narration=narration,
                    on_screen_text=on_screen_text,
                    title=title,
                    video_format=video_format,
                )
            elif not narration:
                narration = _synthesize_narration_from_visual(visual)
            if narration and visual:
                segments.append(
                    ScriptSegment(
                        narration=narration,
                        visual_prompt=visual,
                        on_screen_text=on_screen_text,
                    )
                )

    if not segments:
        segments = [
            ScriptSegment(
                narration="Here’s what people are talking about—and why it’s worth your attention.",
                visual_prompt="bold vertical short graphic look, dynamic composition, readable shapes, 9:16",
                on_screen_text="HOOK",
            )
        ]

    return VideoPackage(
        title=title,
        description=description,
        hashtags=hashtags,
        hook=hook,
        segments=segments,
        cta=cta,
    )


def video_package_from_llm_output(text: str, *, video_format: str = "") -> VideoPackage:
    """Parse model output (JSON, possibly fenced) into a VideoPackage.

    ``video_format`` is forwarded into :func:`_to_package` so the
    visual-prompt synthesis in Phase 3 produces format-aware fallbacks for
    segments where the LLM omitted ``visual_prompt``. Older callers that omit
    ``video_format`` get a generic 9:16 short framing.
    """
    return _to_package(_extract_json(text), video_format=video_format)
def _fallback_package_custom(
    *,
    creative_brief: str,
    items: list[dict[str, str]],
    personality_id: str,
    topic_tags: list[str] | None,
    branding: BrandingSettings | None = None,
) -> VideoPackage:
    personality = get_personality_by_id(personality_id)
    title_seed = (items[0].get("title") if items else "") or creative_brief.strip().splitlines()[0]
    title = (title_seed or "Custom video")[:80]
    blurb = creative_brief.strip()
    if len(blurb) > 280:
        blurb = blurb[:277] + "…"
    hook = title_seed[:120] if title_seed else "Here’s the rundown you asked for—fast and sharp."
    hashtags = ["#Shorts", "#Video", "#Creator", "#Storytelling", "#Watch"]
    for t in topic_tags or []:
        t2 = re.sub(r"[^A-Za-z0-9]+", "", (t or "").strip())
        if t2:
            hashtags.append("#" + t2[:28])
    hashtags = _normalize_hashtags(hashtags)[:30]
    segs = [
        ScriptSegment(
            narration=creative_brief[:320] + ("…" if len(creative_brief) > 320 else ""),
            visual_prompt="bold vertical short graphic opener, dynamic composition, readable shapes, 9:16",
            on_screen_text="HOOK",
        ),
        ScriptSegment(
            narration="Breaking it down: the key ideas from your brief, in plain language.",
            visual_prompt="clean infographic panels, strong typography, vertical 9:16",
            on_screen_text="BREAKDOWN",
        ),
        ScriptSegment(
            narration="Why it lands: quick payoff for viewers who want clarity—not filler.",
            visual_prompt="dynamic icons and timeline, bold color blocks, 9:16",
            on_screen_text="WHY IT MATTERS",
        ),
        ScriptSegment(
            narration=f"Closing thought—keep it {personality.label.lower()} and actionable.",
            visual_prompt="simple bold outro frame, graphic emphasis, 9:16",
            on_screen_text="OUTRO",
        ),
    ]
    pkg = VideoPackage(
        title=title,
        description=blurb or "Custom brief video generated from your instructions.",
        hashtags=hashtags,
        hook=hook,
        segments=segs,
        cta="Follow for more shorts like this.",
    )
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        suf = palette_prompt_suffix(branding)
        if suf:
            pkg = VideoPackage(
                title=pkg.title,
                description=pkg.description,
                hashtags=pkg.hashtags,
                hook=pkg.hook,
                segments=[
                    ScriptSegment(
                        narration=s.narration,
                        visual_prompt=(s.visual_prompt if "Palette:" in s.visual_prompt else f"{s.visual_prompt}, {suf}"),
                        on_screen_text=s.on_screen_text,
                    )
                    for s in pkg.segments
                ],
                cta=pkg.cta,
            )
    return pkg


def enforce_arc(pkg: VideoPackage, video_format: str | None = None) -> VideoPackage:
    """
    Best-effort post-processor to ensure the script includes context + why-it-matters beats.
    We don't require the model to label beats; we inject minimal beats if missing.
    Skipped for cartoon/unhinged/creepypasta/nsfw — comedy, horror, or performer pacing should not get generic "news explainer" inserts.
    """
    vf = (video_format or "news").strip().lower()
    if vf in ("cartoon", "unhinged", "creepypasta", "nsfw"):
        return pkg
    try:
        segs = list(pkg.segments or [])
    except Exception:
        return pkg

    # Heuristics: look for context/why language.
    all_text = " ".join([(pkg.hook or "")] + [s.narration for s in segs] + [(pkg.cta or "")]).lower()
    has_context = any(k in all_text for k in ("here’s what it is", "what it is", "it lets you", "it helps you", "it does", "context"))
    has_why = any(k in all_text for k in ("why it matters", "so what", "this matters because", "impact", "useful because", "the takeaway"))

    insertions: list[ScriptSegment] = []
    if not has_context:
        insertions.append(
            ScriptSegment(
                narration="Quick context — here’s what’s actually going on.",
                visual_prompt="bold vertical infographic panels, clear labels, high contrast, modern short-form graphics, 9:16",
                on_screen_text="CONTEXT",
            )
        )
    if not has_why:
        insertions.append(
            ScriptSegment(
                narration="And here’s why this matters for anyone watching.",
                visual_prompt="dynamic timeline or impact icons, bold typography, vertical 9:16",
                on_screen_text="WHY IT MATTERS",
            )
        )

    if not insertions:
        return pkg

    # Place insertions after first segment if possible.
    out: list[ScriptSegment] = []
    if segs:
        out.append(segs[0])
        out.extend(insertions)
        out.extend(segs[1:])
    else:
        out = insertions

    # Keep overall beat count sane (allow longer LLM scripts after richer prompts).
    _max_arc_segments = 18
    out = out[: min(_max_arc_segments, len(out))]
    return VideoPackage(
        title=pkg.title,
        description=pkg.description,
        hashtags=list(pkg.hashtags),
        hook=pkg.hook,
        segments=out,
        cta=pkg.cta,
    )
