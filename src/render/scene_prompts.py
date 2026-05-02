"""Scene-prompt builder for Pro mode (Phase 4).

The legacy ``_split_into_pro_scenes_from_script`` in ``main.py`` mostly worked
but had three concrete failure modes visible in the
``Two_Sentenced_Horror_Stories`` run:

1. **Forced ``title | `` prefix** for news/explainer formats meant every clip
   asked the T2V model to render the article headline — which CLIP-class
   encoders interpret as a literal text rendering request and which tends to
   collapse all clips into the same shot.
2. **Character-blind comedy/horror prompts**: the cartoon/unhinged path used
   only ``segment.visual_prompt`` text and never injected the cast names or
   the per-character ``visual_style``, so the resulting clips drifted toward
   stock animation regardless of who was supposed to be on screen.
3. **No LLM expansion** when segments < ``n_scenes``: a 2-segment script
   produced 2 scene prompts even though Pro mode wanted 6, leading to
   identical clips repeated.

This module centralises the build into a single deterministic pipeline:

- :class:`SceneSpec` -- per-scene record (prompt + role + style affix).
- :func:`build_scene_prompts` -- main entry point. Pure-Python; never imports
  the LLM or torch.
- :func:`expand_scenes_via_llm` -- optional LLM extender. Lazy-imports
  ``brain`` so unit tests don't pay the cost.

The module deliberately *omits* the headline prefix for every format
(headline goes into branding overlays, not the visual prompt itself) and
adds a per-format genre cue plus a per-scene motion verb so consecutive
clips read as visually distinct.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

#: Words-budget per scene. CLIP-class T2V text encoders are ~77 tokens; ~40
#: words is a safe margin including punctuation and the genre/cue suffix.
SCENE_WORD_CAP: int = 40

#: Hard upper bound on scenes regardless of caller request. Keeps preflight
#: budgets honest for slow T2V models like CogVideoX.
SCENE_COUNT_MAX: int = 16


_NEGATIVE_RE = re.compile(r"\bNEGATIVE\b\s*:.*", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class SceneSpec:
    """One scene's prompt and provenance."""

    prompt: str
    role: str  # "hook" | "segment" | "cta" | "expanded"
    source_index: int  # index into the source list (segments / prompts) or -1


def strip_noise(text: str) -> str:
    """Remove ``NEGATIVE:`` blocks and collapse whitespace."""
    s = (text or "").strip()
    if not s:
        return ""
    s = _NEGATIVE_RE.sub("", s)
    s = " ".join(s.split())
    return s.strip(" ,;:|")


def cap_words(text: str, *, n_words: int = SCENE_WORD_CAP) -> str:
    """Trim *text* to ``n_words`` words while preserving order."""
    parts = [p for p in (text or "").split() if p]
    if len(parts) <= n_words:
        return " ".join(parts).strip()
    return " ".join(parts[: max(1, int(n_words))]).strip()


def _genre_motion_cues(video_format: str) -> tuple[str, ...]:
    """Per-format motion verbs used to keep consecutive scenes visually distinct."""
    vf = (video_format or "news").strip().lower()
    if vf in ("cartoon", "unhinged"):
        return (
            "push-in, whip pan",
            "snap zoom, squash-stretch",
            "handheld wobble",
            "dolly blur",
            "lunge to camera",
            "spin smear",
            "tilt up reveal",
            "match-cut on action",
        )
    if vf == "creepypasta":
        return (
            "slow dolly into darkness",
            "static long lens hold",
            "creeping pan",
            "rack focus through fog",
            "low angle, lamp flicker",
            "match-cut on silhouette",
            "subjective handheld step",
            "slow tilt up to ceiling",
        )
    if vf == "health_advice":
        return (
            "calm push-in",
            "soft parallax drift",
            "static medium shot",
            "rack focus to diagram",
            "gentle pull-back",
        )
    return (
        "slow push-in",
        "parallax drift",
        "gentle pan",
        "rack focus",
        "static establish",
        "subtle handheld",
    )


def _genre_style_tail(video_format: str) -> str:
    """Per-format visual tail appended once when the user has no art-style affix."""
    vf = (video_format or "news").strip().lower()
    return {
        "news": "9:16 vertical, clean editorial framing, readable composition",
        "explainer": "9:16 vertical, clean infographic-friendly framing",
        "cartoon": "9:16 vertical, bold flat 2D animation, expressive acting",
        "unhinged": "9:16 vertical, satirical adult-animation, exaggerated reaction",
        "creepypasta": "9:16 vertical, low-key cinematic horror, fog and grain, no gore",
        "health_advice": "9:16 vertical, soft clinical teaching look, no real patients",
    }.get(vf, "9:16 vertical, cinematic framing")


def _character_phrase(character_names: Sequence[str], idx: int) -> str:
    """Return ``"Foo and Bar"`` (cycling through the cast) for scene *idx*."""
    names = [str(n).strip() for n in character_names if str(n).strip()]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    a = names[idx % len(names)]
    b = names[(idx + 1) % len(names)]
    return f"{a} and {b}"


def _extract_character_names(character_context: str | None) -> list[str]:
    """Parse cast names from the brain ``character_context`` block.

    Looks for ``- Name (role)`` and ``- Name: ...`` bullets first; falls back
    to ``Cast: Name & Other`` headings; finally to a stand-alone
    ``Character name: <name>`` line (single-narrator formats).
    """
    if not character_context:
        return []
    out: list[str] = []
    for line in character_context.splitlines():
        m = re.match(r"^\s*-\s*([A-Z][\w' .-]{0,80})(?:\s*\(.*\))?(?::|$)", line)
        if m:
            nm = m.group(1).strip()
            if nm and nm not in out:
                out.append(nm)
    if not out:
        m = re.search(r"^Cast:\s*(.+)$", character_context, re.MULTILINE)
        if m:
            cast_line = m.group(1).strip()
            for nm in re.split(r"[&,]", cast_line):
                nm = nm.strip()
                if nm and nm not in out:
                    out.append(nm)
    if not out:
        m = re.search(r"^Character name:\s*(.+)$", character_context, re.MULTILINE)
        if m:
            nm = m.group(1).strip()
            if nm:
                out.append(nm)
    return out[:4]


def _format_uses_title_anchor(video_format: str) -> bool:
    """Whether to keep any reference to the article headline in the prompt.

    Phase 4 drops the legacy forced ``"<title> | "`` prefix entirely. We keep
    the function as an extension point so a future preset can opt back in.
    """
    return False


def _emphasize_subject(text: str, *, subject: str | None) -> str:
    """Prepend the subject (e.g. cast pair or narrator) when it isn't already there."""
    s = strip_noise(text)
    if not s:
        return s
    if not subject:
        return s
    if subject.lower() in s.lower():
        return s
    return f"{subject}, {s}"


def _ensure_unique_starts(specs: list[SceneSpec]) -> list[SceneSpec]:
    """De-duplicate consecutive scenes that begin with the same 4 words.

    The motion-cue rotation already varies the *end* of each prompt; this
    helper makes sure the *start* doesn't read as the same shot either.
    """
    out: list[SceneSpec] = []
    last_head = ""
    for s in specs:
        head = " ".join(s.prompt.split()[:4]).lower()
        if head and head == last_head and out:
            words = s.prompt.split()
            shifted = " ".join(words[2:] + words[:2]) if len(words) > 4 else s.prompt
            out.append(SceneSpec(prompt=shifted, role=s.role, source_index=s.source_index))
        else:
            out.append(s)
        last_head = head
    return out


def build_scene_prompts(
    *,
    pkg: Any,
    fallback_prompts: Sequence[str] | None = None,
    video_format: str = "news",
    n_scenes: int | None = None,
    character_context: str | None = None,
    art_style_affix: str = "",
    branding_affix: str = "",
) -> list[SceneSpec]:
    """Build a deterministic list of :class:`SceneSpec` from a script package.

    Parameters
    ----------
    pkg:
        Anything with ``title``, ``hook``, ``cta`` strings and ``segments``
        (each having ``narration`` and ``visual_prompt``). We avoid a hard
        type to keep the unit tests free of brain imports.
    fallback_prompts:
        Pre-existing image/video prompts (Storyboard) to use when a segment
        has no ``visual_prompt`` and no narration.
    video_format:
        Drives genre cues and the per-format style tail.
    n_scenes:
        Target number of scenes. ``None`` returns whatever the script yields
        (clamped to :data:`SCENE_COUNT_MAX`). When the script yields fewer
        than ``n_scenes``, callers may pass the result through
        :func:`expand_scenes_via_llm` to top up the list.
    character_context:
        The brain's ``character_context`` block (parsed for cast names).
    art_style_affix:
        Optional comma-joined affix appended once per scene (image side).
    branding_affix:
        Optional comma-joined affix from
        :func:`src.content.prompt_context.StyleContext.as_t2v_affix`.
    """
    vf = (video_format or "news").strip().lower()
    cues = _genre_motion_cues(vf)
    cast = _extract_character_names(character_context)
    title_in_prompt = _format_uses_title_anchor(vf)
    title = " ".join(str(getattr(pkg, "title", "") or "").split()).strip() if title_in_prompt else ""

    style_affix = ", ".join(
        bit
        for bit in (
            art_style_affix.strip(" ,") if art_style_affix else "",
            branding_affix.strip(" ,") if branding_affix else "",
            _genre_style_tail(vf),
        )
        if bit
    )

    specs: list[SceneSpec] = []

    def _push(text: str, *, role: str, source_index: int) -> None:
        body = strip_noise(text)
        if not body:
            return
        subject = _character_phrase(cast, len(specs)) if cast else ""
        body = _emphasize_subject(body, subject=subject or None)
        cue = cues[len(specs) % len(cues)]
        bits = [bit for bit in (title, body, cue, style_affix) if bit]
        prompt = cap_words(", ".join(bits), n_words=SCENE_WORD_CAP)
        specs.append(SceneSpec(prompt=prompt, role=role, source_index=source_index))

    segments = list(getattr(pkg, "segments", None) or [])

    hook_text = str(getattr(pkg, "hook", "") or "").strip()
    if hook_text:
        seg_visual = ""
        if segments:
            seg_visual = " ".join(str(getattr(segments[0], "visual_prompt", "") or "").split()).strip()
        _push(seg_visual or hook_text, role="hook", source_index=-1)

    for i, seg in enumerate(segments):
        if vf in ("cartoon", "unhinged", "creepypasta"):
            text = " ".join(str(getattr(seg, "visual_prompt", "") or "").split()).strip()
            if not text:
                text = " ".join(str(getattr(seg, "narration", "") or "").split()).strip()
        else:
            text = " ".join(str(getattr(seg, "narration", "") or "").split()).strip()
            if not text:
                text = " ".join(str(getattr(seg, "visual_prompt", "") or "").split()).strip()
        if text:
            _push(text, role="segment", source_index=i)

    cta_text = str(getattr(pkg, "cta", "") or "").strip()
    if cta_text:
        seg_visual = ""
        if segments:
            seg_visual = " ".join(str(getattr(segments[-1], "visual_prompt", "") or "").split()).strip()
        _push(seg_visual or cta_text, role="cta", source_index=-1)

    if not specs and fallback_prompts:
        for i, p in enumerate(fallback_prompts):
            _push(p, role="segment", source_index=i)
            if len(specs) >= 8:
                break

    if not specs:
        _push(
            getattr(pkg, "title", "") or "cinematic vertical short, cohesive subject",
            role="segment",
            source_index=0,
        )

    specs = _ensure_unique_starts(specs)

    if n_scenes is not None:
        target = max(1, min(int(n_scenes), SCENE_COUNT_MAX))
        if len(specs) > target:
            return specs[:target]
    return specs[:SCENE_COUNT_MAX]


def expand_scenes_via_llm(
    specs: list[SceneSpec],
    *,
    target_count: int,
    video_format: str,
    character_context: str | None,
    invoke_llm: Callable[[str], str] | None = None,
) -> list[SceneSpec]:
    """Top up *specs* with additional scenes generated by the script LLM.

    No-op when ``len(specs) >= target_count``.

    The caller passes ``invoke_llm`` -- a single-shot callable that takes a
    user prompt and returns generated text. We keep this indirection so unit
    tests can stub the LLM without importing the heavy brain stack.
    """
    target = max(1, min(int(target_count), SCENE_COUNT_MAX))
    if len(specs) >= target:
        return specs[:target]
    if invoke_llm is None:
        return specs[:target]

    cues = _genre_motion_cues(video_format)
    cast_names = _extract_character_names(character_context)
    needed = target - len(specs)

    seed_prompts = "\n".join(f"- {s.prompt}" for s in specs)
    cast_line = ", ".join(cast_names) if cast_names else "(narrator only)"
    user_prompt = (
        "You are filling in extra scene prompts for a short-form vertical video.\n"
        f"Video format: {video_format}\n"
        f"Cast: {cast_line}\n"
        f"Existing scene prompts (do NOT repeat verbatim):\n{seed_prompts}\n\n"
        f"Generate {needed} ADDITIONAL distinct scene prompts that bridge or extend the existing ones.\n"
        "Rules:\n"
        f"- Each prompt under {SCENE_WORD_CAP} words.\n"
        "- Vertical 9:16 framing.\n"
        "- No NEGATIVE: blocks. No JSON, no bullets, no numbering.\n"
        "- One prompt per line.\n"
        "- Do not include the article headline.\n"
        "- Use the cast names where appropriate so visual continuity is preserved.\n"
    )
    try:
        raw = invoke_llm(user_prompt) or ""
    except Exception:
        return specs

    extras: list[SceneSpec] = []
    for i, line in enumerate(raw.splitlines()):
        text = strip_noise(line)
        text = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", text)
        if not text:
            continue
        cue = cues[(len(specs) + i) % len(cues)]
        prompt = cap_words(f"{text}, {cue}", n_words=SCENE_WORD_CAP)
        extras.append(SceneSpec(prompt=prompt, role="expanded", source_index=-1))
        if len(specs) + len(extras) >= target:
            break

    out = list(specs) + extras
    return _ensure_unique_starts(out)[:target]


def specs_to_prompts(specs: Iterable[SceneSpec]) -> list[str]:
    """Flatten :class:`SceneSpec` items to a plain ``list[str]`` for the renderer."""
    return [s.prompt for s in specs if s.prompt]
