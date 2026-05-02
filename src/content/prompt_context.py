"""Phase 9 — fuse video_format, personality, art_style, and branding into one
prompt-context block reused by every text stage (script LLM, scene-prompt
builder, T2V/T2I affixes).

Why
---
Pre-Phase-9 each stage hand-rolled its own copy of the same four signals:

* The script LLM saw `personality.style_rules` + `branding` palette + the
  `_character_voice_block`.
* The T2I builder (`src/render/artist.py`) saw the `art_style_preset_id`
  affix + the same branding palette.
* The T2V builder saw nothing about the art style at all in some paths.
* Conflicts (e.g. `creepypasta` + `Hype / Creator` personality) were never
  caught — runs ended up with horror beats narrated by a peppy creator.

`StyleContext` resolves all four sources once, surfaces conflicts, and emits
ready-to-paste prompt blocks for each surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.content.personalities import PersonalityPreset, get_personality_by_id


_FORMAT_VOICE_LOCK: dict[str, str] = {
    "creepypasta": (
        "Default voice: first-person past-tense campfire narrator (or tight third person if the "
        "character block requires it); not a peppy news host."
    ),
    "unhinged": (
        "Default voice: chaotic adult-cartoon ensemble — quick interjections, deadpan asides, no "
        "newsroom delivery, no straight tutorial pacing."
    ),
    "cartoon": (
        "Default voice: animated character voice — playful and expressive; let the personality "
        "preset shape pace, but keep the character vibe intact."
    ),
    "health_advice": (
        "Default voice: calm, evidence-based explainer; warm but clinical accuracy; never alarmist."
    ),
    "news": (
        "Default voice: neutral newsroom presenter; factual, no slang, no drama overshoot."
    ),
    "explainer": (
        "Default voice: friendly explainer; structured (problem → solution → trade-off); concrete examples."
    ),
}

# Personalities that conflict with horror / chaos formats. Each entry is
# (format, personality_id) → human-readable warning.
_CONFLICTS: dict[tuple[str, str], str] = {
    ("creepypasta", "hype"): "Hype / Creator energy clashes with creepypasta dread; switching to neutral / cozy reading.",
    ("creepypasta", "comedic"): "Comedic punchlines undercut horror dread; switching to neutral.",
    ("unhinged", "neutral"): "Neutral newsroom delivery reads flat for unhinged sketches; switching to comedic.",
    ("unhinged", "cozy"): "Cozy explainer is too gentle for unhinged sketches; switching to comedic.",
    ("health_advice", "unhinged_chaos"): "Chaotic delivery contradicts health-advice safety guidance; switching to cozy.",
    ("news", "comedic"): "Comedic delivery may undercut news clarity; switching to neutral.",
}

_CONFLICT_REPLACEMENTS: dict[tuple[str, str], str] = {
    ("creepypasta", "hype"): "neutral",
    ("creepypasta", "comedic"): "neutral",
    ("unhinged", "neutral"): "comedic",
    ("unhinged", "cozy"): "comedic",
    ("health_advice", "unhinged_chaos"): "cozy",
    ("news", "comedic"): "neutral",
}


def format_voice_lock(video_format: str | None) -> str:
    vf = (video_format or "").strip().lower()
    return _FORMAT_VOICE_LOCK.get(vf, "")


def reconcile_format_personality(
    video_format: str | None, personality: PersonalityPreset | None
) -> tuple[PersonalityPreset, list[str]]:
    """Return ``(effective_personality, warnings)``.

    When the original personality conflicts with the format we swap to a
    sane default (defined in ``_CONFLICT_REPLACEMENTS``) and surface a
    human-readable warning. Callers can include the warning in pipeline
    notices, prompts, or logs.
    """
    p = personality
    if p is None:
        p = get_personality_by_id("neutral")
    vf = (video_format or "").strip().lower()
    warnings: list[str] = []
    key = (vf, getattr(p, "id", "") or "")
    if key in _CONFLICTS:
        warnings.append(_CONFLICTS[key])
        replacement = _CONFLICT_REPLACEMENTS.get(key)
        if replacement:
            try:
                p = get_personality_by_id(replacement)
            except Exception:
                pass
    return p, warnings


def art_style_text_affix(art_style_id: str | None) -> str:
    aid = (art_style_id or "").strip().lower()
    if not aid:
        return ""
    try:
        from src.settings.art_style_presets import ART_STYLE_PRESETS

        for p in ART_STYLE_PRESETS:
            if p.id.lower() == aid:
                return p.prompt_affix
    except Exception:
        pass
    return ""


def art_style_negative_affix(art_style_id: str | None) -> str:
    aid = (art_style_id or "").strip().lower()
    if not aid:
        return ""
    try:
        from src.settings.art_style_presets import ART_STYLE_PRESETS

        for p in ART_STYLE_PRESETS:
            if p.id.lower() == aid:
                return p.negative_affix
    except Exception:
        pass
    return ""


def branding_to_prompt_block(branding: Any | None) -> str:
    """One block summarizing the user's branding palette / style strength."""
    if branding is None:
        return ""
    try:
        from src.render.branding_video import palette_prompt_suffix, video_style_strength

        if not bool(getattr(branding, "video_style_enabled", False)):
            return ""
        suf = palette_prompt_suffix(branding) or ""
        if not suf:
            return ""
        strength = video_style_strength(branding)
        return f"Branding (strength={strength}): {suf}"
    except Exception:
        return ""


def _personality_summary(p: PersonalityPreset | None) -> str:
    if p is None:
        return ""
    rules = " / ".join(getattr(p, "style_rules", []) or [])
    do_dont = " / ".join(getattr(p, "do_dont", []) or [])
    bits = [f"{p.label} — {p.description}"]
    if rules:
        bits.append(f"rules: {rules}")
    if do_dont:
        bits.append(f"guardrails: {do_dont}")
    return " | ".join(bits)


@dataclass(frozen=True)
class StyleContext:
    video_format: str
    personality: PersonalityPreset | None
    art_style_id: str
    branding: Any | None = None
    character_context: str | None = None
    conflict_warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def format_voice_lock(self) -> str:
        return format_voice_lock(self.video_format)

    @property
    def art_affix(self) -> str:
        return art_style_text_affix(self.art_style_id)

    @property
    def art_negative_affix(self) -> str:
        return art_style_negative_affix(self.art_style_id)

    @property
    def branding_block(self) -> str:
        return branding_to_prompt_block(self.branding)

    def as_script_prompt_block(self) -> str:
        """One Markdown block that the script LLM prompt can append wholesale."""
        lines: list[str] = ["## Style fusion (applies to ALL segments)"]
        if self.video_format:
            lines.append(f"- Video format: {self.video_format}")
        if self.format_voice_lock:
            lines.append(f"- {self.format_voice_lock}")
        ps = _personality_summary(self.personality)
        if ps:
            lines.append(f"- Personality: {ps}")
        if self.art_affix:
            lines.append(f"- Art style: {self.art_affix}")
        if self.art_negative_affix:
            lines.append(f"- Art style negatives: {self.art_negative_affix}")
        if self.branding_block:
            lines.append(f"- {self.branding_block}")
        if self.character_context:
            lines.append("- Character (host) is provided in a separate block; honor it for narration only.")
        if self.conflict_warnings:
            lines.append("- Conflict notices:")
            for w in self.conflict_warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines) + "\n"

    def as_t2i_affix(self) -> str:
        """Short comma-separated affix for image (T2I) prompts."""
        bits: list[str] = []
        if self.art_affix:
            bits.append(self.art_affix)
        if self.branding_block:
            bits.append(self.branding_block.split(": ", 1)[-1])
        return ", ".join(b for b in bits if b)

    def as_t2v_affix(self) -> str:
        """Short comma-separated affix for video (T2V) prompts."""
        bits: list[str] = []
        if self.art_affix:
            bits.append(self.art_affix)
        if self.branding_block:
            bits.append(self.branding_block.split(": ", 1)[-1])
        if self.video_format == "creepypasta":
            bits.append("dim moody atmospheric lighting")
        elif self.video_format == "cartoon":
            bits.append("bold linework, dynamic camera")
        elif self.video_format == "unhinged":
            bits.append("exaggerated character expressions, chaotic energy")
        return ", ".join(b for b in bits if b)


def _coerce_iterable_warnings(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(v).strip() for v in values if str(v).strip())


def compose_prompt_context(
    *,
    app: Any,
    character_context: str | None = None,
    extra_warnings: Iterable[str] | None = None,
) -> StyleContext:
    """Assemble a :class:`StyleContext` from an :class:`AppSettings` object."""
    vf = str(getattr(app, "video_format", "news") or "news").strip().lower()
    personality_id = str(getattr(app, "personality_id", "neutral") or "neutral").strip().lower()
    if personality_id in {"", "auto"}:
        personality_id = "neutral"
    try:
        original = get_personality_by_id(personality_id)
    except Exception:
        original = None
    personality, conflicts = reconcile_format_personality(vf, original)
    art_style_id = str(getattr(app, "art_style_preset_id", "") or "").strip().lower()
    branding = getattr(app, "branding", None)
    warnings = list(conflicts) + list(_coerce_iterable_warnings(extra_warnings))
    return StyleContext(
        video_format=vf,
        personality=personality,
        art_style_id=art_style_id,
        branding=branding,
        character_context=character_context,
        conflict_warnings=tuple(warnings),
    )


_WHITESPACE_RE = re.compile(r"\s+")


def merge_with_supplement(supplement: str | None, ctx: StyleContext) -> str:
    """Append the script-prompt block to an existing supplement_context string."""
    block = ctx.as_script_prompt_block().strip()
    sup = (supplement or "").strip()
    if not block:
        return sup
    if not sup:
        return block + "\n"
    if block in sup:
        return sup
    return f"{sup}\n\n{block}\n"
