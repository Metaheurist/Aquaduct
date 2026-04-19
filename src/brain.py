from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .utils_vram import cleanup_vram, vram_guard
from .personalities import PersonalityPreset, get_personality_by_id
from .character_presets import (
    CharacterAutoPreset,
    GeneratedCharacterFields,
    coerce_generated_character_fields,
    extract_first_json_object,
)
from .config import BrandingSettings, get_paths
from .model_manager import resolve_pretrained_load_path
from .branding_video import palette_prompt_suffix, video_style_strength
from debug import dprint


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
    # Prefer fenced block
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if m:
        return json.loads(m.group(1))

    # Otherwise try first {...} span
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("No JSON object found in model output.")


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


def _to_package(data: dict[str, Any]) -> VideoPackage:
    title = str(data.get("title", "")).strip() or "AI Tool Review"
    description = str(data.get("description", "")).strip()
    if not description:
        description = "Quick breakdown of a new AI tool release: what it does, why it matters, and who should try it."

    hashtags = _normalize_hashtags(data.get("hashtags", []) if isinstance(data.get("hashtags"), list) else [])
    if not hashtags:
        hashtags = ["#AI", "#AITools", "#TechTok", "#Productivity", "#AInews"]

    hook = str(data.get("hook", "")).strip()
    cta = str(data.get("cta", "")).strip() or "Follow for daily AI tool drops and fast reviews."

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
            if narration and visual:
                segments.append(ScriptSegment(narration=narration, visual_prompt=visual, on_screen_text=on_screen_text))

    if not segments:
        # Minimal fallback structure
        segments = [
            ScriptSegment(
                narration="Here’s the new AI tool everyone’s testing—and why it’s useful.",
                visual_prompt="high-contrast cyberpunk UI, neon holographic interface, close-up, sharp, 9:16 composition",
                on_screen_text="NEW AI TOOL",
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


def _prompt_for_unhinged_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
) -> str:
    """Preset prompts for 'unhinged' adult-animation-style satire (not AI tool reviews)."""
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = f"Topic tags (bias hashtags and story angle): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
    personality_block = (
        "Tone/personality:\n"
        f"- {personality.label}\n"
        f"- {personality.description}\n"
        "Style rules:\n"
        + "\n".join(f"- {r}" for r in personality.style_rules)
        + "\nDo/Don't:\n"
        + "\n".join(f"- {r}" for r in personality.do_dont)
        + "\n"
    )
    style_suffix = ""
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        strength = video_style_strength(branding)
        suf = palette_prompt_suffix(branding)
        if suf:
            style_suffix = (
                "Visual palette guidance:\n"
                f"- Strength: {strength}\n"
                f"- {suf}\n"
            )
    char_block = ""
    cc = (character_context or "").strip()
    if cc:
        char_block = (
            "Character / host identity (layer on tone; stay consistent in narration and on-screen cues):\n"
            f"{cc}\n\n"
        )
    return (
        "You are a comedy writer for chaotic vertical shorts (9:16). Write an UNHINGED CARTOON script in the spirit of "
        "prestige adult-animation comedy: absurdist dread and awkward pauses, cynical sci-fi or family-sitcom banter, "
        "shock-satire punchlines, grotesque-cute or liminal-weird imagery — like classic adult animated sitcoms, "
        "NOT kids' TV or product reviews. Do not name, quote, or imitate any real show, character, or creator; "
        "invent original voices and settings. Stay playful; no slurs, hate, harassment, or real-person cruelty.\n"
        "Headlines below skew toward internet culture / viral stories — pick ONE as a loose seed to satirize "
        "(twist or parody freely; this is NOT a neutral news report and NOT a tutorial).\n"
        "Storytelling rule: The `hook` and every segment's `narration` must be in character voice — "
        "first-person, dialogue between characters, or close third tied to a named character. "
        "Do NOT default to a neutral news announcer; the story is told through the cast.\n"
        "Write a ~50 second script with 6-10 few-second beats. Each beat should feel like a different voice could deliver it "
        "(snappy, quotable lines; deadpan or manic energy both work).\n"
        "Visual style: exaggerated 2D adult-animation look — flat color, rubber-hose or sharp TV-comedy staging, "
        "gross-out or surreal backgrounds when it sells the joke — NOT corporate cyberpunk unless the joke demands it.\n"
        "Enforce this structure (keep it tight):\n"
        "- Hook (0-2s): wrong-foot the viewer — fake-wholesome, deadpan doom, or sudden satire\n"
        "- Escalation (2-18s): the premise spirals (sitcom argument, sci-fi nonsense, or moral panic)\n"
        "- Chaos peak (18-35s): maximum cartoon transgression with one concrete visual gag per beat\n"
        "- Payoff (35-45s): land the joke (bleeped energy ok in text; no real slurs)\n"
        "- Close/CTA (last few seconds): ironic follow / subscribe bit\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        "- narration total ~120-150 words\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items mixing adult animation + satire + cartoon comedy + shorts tags "
        "(e.g. #AdultAnimation #CartoonTok), not only #AI\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{style_suffix}"
        f"{tag_line}"
        f"Headlines (pick ONE as seed — interpret wildly): {json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_cartoon_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
) -> str:
    """Preset prompts for cartoon format — character-voiced story, not news reviews."""
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = f"Topic tags (bias hashtags and story angle): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
    personality_block = (
        "Tone/personality:\n"
        f"- {personality.label}\n"
        f"- {personality.description}\n"
        "Style rules:\n"
        + "\n".join(f"- {r}" for r in personality.style_rules)
        + "\nDo/Don't:\n"
        + "\n".join(f"- {r}" for r in personality.do_dont)
        + "\n"
    )
    style_suffix = ""
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        strength = video_style_strength(branding)
        suf = palette_prompt_suffix(branding)
        if suf:
            style_suffix = (
                "Visual palette guidance:\n"
                f"- Strength: {strength}\n"
                f"- {suf}\n"
            )
    char_block = ""
    cc = (character_context or "").strip()
    if cc:
        char_block = (
            "Character / cast (the story is told through these voices — stay consistent):\n"
            f"{cc}\n\n"
        )
    return (
        "You are a comedy writer for playful cartoon vertical shorts (9:16). "
        "Tell a tiny story with a clear beginning, middle, and punchline — all through characters.\n"
        "Storytelling rule: The `hook` and every segment's `narration` must be in character voice — "
        "first-person, dialogue between characters, or close third tied to a named character. "
        "Do NOT use a neutral TV announcer or product-demo narrator unless the joke is explicitly about that. "
        "The audience should hear the cast living the story.\n"
        "Pick ONE headline below as a loose seed — these favor **new animation / cartoon buzz** (releases, trailers, streaming news). "
        "Parody or twist freely. Do NOT write a tutorial, drawing lesson, or step-by-step explainer; stay comedy/entertainment.\n"
        "Write a ~50 second script with 6-10 few-second beats. Keep language family-friendly; no slurs or hate.\n"
        "Visual style: bright 2D cartoon, bold shapes, expressive faces, rubber-hose or modern toon energy.\n"
        "Enforce this structure (keep it tight):\n"
        "- Hook (0-2s): a character grabs the mic — wrong-footing or playful chaos\n"
        "- Rising action (2-22s): characters react, escalate, argue, or chase the idea\n"
        "- Peak (22-38s): biggest visual gag; one concrete cartoon beat per segment when possible\n"
        "- Payoff (38-48s): land the joke from the cast's POV\n"
        "- Close/CTA (last few seconds): in-character sign-off\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Use `on_screen_text` for short dialogue tags, reactions, or caption jokes.\n"
        "Constraints:\n"
        "- narration total ~120-150 words\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items mixing cartoon + comedy + shorts tags (e.g. #CartoonTok), not only #AI\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{style_suffix}"
        f"{tag_line}"
        f"Headlines (pick ONE as seed — interpret wildly): {json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    video_format: str = "news",
) -> str:
    vf = (video_format or "news").strip().lower()
    if vf == "cartoon":
        return _prompt_for_cartoon_items(
            headlines, topic_tags, personality, branding=branding, character_context=character_context
        )
    if vf == "unhinged":
        return _prompt_for_unhinged_items(
            headlines, topic_tags, personality, branding=branding, character_context=character_context
        )
    # Keep it stable for JSON parsing.
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = f"Topic tags (must strongly influence the tool choice/angle): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
    personality_block = (
        "Tone/personality:\n"
        f"- {personality.label}\n"
        f"- {personality.description}\n"
        "Style rules:\n"
        + "\n".join(f"- {r}" for r in personality.style_rules)
        + "\nDo/Don't:\n"
        + "\n".join(f"- {r}" for r in personality.do_dont)
        + "\n"
    )

    style_suffix = ""
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        strength = video_style_strength(branding)
        suf = palette_prompt_suffix(branding)
        if suf:
            style_suffix = (
                "Visual palette guidance:\n"
                f"- Strength: {strength}\n"
                f"- {suf}\n"
            )
    char_block = ""
    cc = (character_context or "").strip()
    if cc:
        char_block = (
            "Character / host identity (layer on top of tone/personality; stay consistent in narration and on-screen cues):\n"
            f"{cc}\n\n"
        )
    return (
        "You are a viral short-form scriptwriter focused on AI tool reviews.\n"
        "Write a ~50 second vertical video script with 6-10 few-second beats.\n"
        "Style: punchy, factual, no fluff. Visual style: high-contrast cyberpunk.\n"
        "Enforce this structure (keep it tight):\n"
        "- Hook (0-2s): one punchy line\n"
        "- Context (2-6s): what it is / what's new\n"
        "- Key points (6-20s): 2-3 concrete points\n"
        "- Why it matters (20-30s): practical impact / who should care\n"
        "- Close/CTA (last 2s): short follow/subscribe style line\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        "- narration total ~120-150 words\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items, each like \"#AITools\"\n"
        "- mention the tool name early\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{style_suffix}"
        f"{tag_line}"
        f"Headlines (pick ONE main tool release to review): {json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _vf_hint(video_format: str) -> str:
    f = (video_format or "news").strip().lower()
    # News + Explainer: same short-form "AI news" voice and structure (see _prompt_for_items).
    if f in ("news", "explainer"):
        return "timely angle; connect to current AI tooling news when plausible"
    if f == "cartoon":
        return (
            "character-driven cartoon comedy riffing on fresh animation/cartoon headlines (releases, trailers, buzz) — "
            "entertainment only; not a tutorial, not a how-to lesson"
        )
    if f == "unhinged":
        return (
            "adult-animation comedy satirizing internet trends / viral discourse — absurdist satire, cynical banter, "
            "shock-cartoon punchlines; invent original characters — no cruelty or hate, playful only"
        )
    return "timely angle; connect to current AI tooling news when plausible"


def _prompt_for_creative_brief(
    *,
    expanded_brief: str,
    topic_tags: list[str] | None,
    video_format: str,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
) -> str:
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = (
        f"Topic tags (optional; bias hashtags and angle if relevant): {json.dumps(tags, ensure_ascii=False)}\n"
        if tags
        else ""
    )
    personality_block = (
        "Tone/personality:\n"
        f"- {personality.label}\n"
        f"- {personality.description}\n"
        "Style rules:\n"
        + "\n".join(f"- {r}" for r in personality.style_rules)
        + "\nDo/Don't:\n"
        + "\n".join(f"- {r}" for r in personality.do_dont)
        + "\n"
    )
    style_suffix = ""
    if branding and bool(getattr(branding, "video_style_enabled", False)):
        strength = video_style_strength(branding)
        suf = palette_prompt_suffix(branding)
        if suf:
            style_suffix = (
                "Visual palette guidance:\n"
                f"- Strength: {strength}\n"
                f"- {suf}\n"
            )
    char_block = ""
    cc = (character_context or "").strip()
    if cc:
        char_block = (
            "Character / host identity (layer on top of tone/personality; stay consistent in narration and on-screen cues):\n"
            f"{cc}\n\n"
        )
    vf = _vf_hint(video_format)
    vf_key = (video_format or "news").strip().lower()
    if vf_key == "cartoon":
        return (
            "You are a comedy writer for cartoon vertical shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            "Narration must be in character voice throughout (dialogue or first-person), not a detached announcer.\n"
            "Default visual style: bright 2D cartoon, expressive acting — unless the brief says otherwise.\n"
            "Enforce this structure (keep it tight):\n"
            "- Hook (0-2s): a character opens\n"
            "- Rising action (2-22s): cast drives the story\n"
            "- Peak (22-38s): biggest gag\n"
            "- Payoff + CTA: in-character close\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            "- narration total ~120-150 words\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items mixing cartoon + comedy + shorts tags\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
        )
    if vf_key == "unhinged":
        return (
            "You are a comedy writer for adult-animation-style vertical shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            "Write a ~50 second script with 6-10 few-second beats. Do not name or imitate real shows or characters; invent originals.\n"
            "Narration must be in character voice throughout — not a neutral news announcer.\n"
            "Default visual style: flat 2D adult-animation satire, exaggerated acting, gross-out or surreal sets — "
            "unless the brief says otherwise (not corporate cyberpunk by default).\n"
            "Enforce this structure (keep it tight):\n"
            "- Hook (0-2s): deadpan wrongness or fake-sincere doom\n"
            "- Escalation (2-18s): sitcom argument, sci-fi nonsense, or moral panic — pick one and spiral\n"
            "- Chaos peak (18-35s): maximum cartoon transgression; one concrete visual gag per beat\n"
            "- Payoff (35-45s): land the joke\n"
            "- Close/CTA (last few seconds): ironic follow / subscribe bit\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            "- narration total ~120-150 words\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items mixing adult animation + satire + cartoon comedy + shorts tags\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
        )
    return (
        "You are a viral short-form scriptwriter for vertical video (9:16).\n"
        "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
        "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
        f"Video format mode: {video_format!r}. Aim for: {vf}\n"
        "Write a ~50 second vertical video script with 6-10 few-second beats.\n"
        "Style: punchy, factual where needed, no fluff. Default visual style: high-contrast cyberpunk unless the brief says otherwise.\n"
        "Enforce this structure (keep it tight):\n"
        "- Hook (0-2s): one punchy line\n"
        "- Context (2-6s): what it is / setup\n"
        "- Key points (6-20s): 2-3 concrete points\n"
        "- Why it matters (20-30s): practical impact / who should care\n"
        "- Close/CTA (last 2s): short follow/subscribe style line\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        "- narration total ~120-150 words\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items, each like \"#AITools\"\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{style_suffix}"
        f"{tag_line}"
        "Creative brief (primary — follow this):\n"
        f"{expanded_brief.strip()}\n"
    )


def expand_custom_video_instructions(
    *,
    model_id: str,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    try_llm_4bit: bool = True,
) -> str:
    """
    First LLM pass for custom Run mode: expand the user's rough notes into a structured creative brief (plain text).
    """
    personality = get_personality_by_id(personality_id)
    vf = _vf_hint(video_format)
    vf_key = (video_format or "news").strip().lower()
    if vf_key == "cartoon":
        prompt = (
            "You are a creative director for character-driven cartoon shorts (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "The story must be told through characters — specify who speaks, their voices, and how narration maps to beats.\n"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Cast (names + one-line voice each)\n"
            "3) Core hook (in-character)\n"
            "4) Beat-by-beat outline (6–10 beats for ~50 seconds) — who says what\n"
            "5) Visual motifs (bright 2D cartoon; not cyberpunk unless notes say so)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea (in-character)\n"
            "Keep it tight and actionable.\n"
        )
    elif vf_key == "unhinged":
        prompt = (
            "You are a creative director for adult-animation-style comedy shorts (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Comedy direction: absurdist satire, cynical banter, shock-cartoon or surreal dread — "
            "invent original characters and settings; do not name or imitate real shows.\n"
            "The story must be told through those characters' voices (not a neutral announcer).\n"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Cast (who speaks; one-line voice each)\n"
            "3) Core angle / hook (deadpan, wrong-footing, or satirical)\n"
            "4) Beat-by-beat outline (6–10 beats for ~50 seconds total) — who says what\n"
            "5) Visual motifs (default: flat 2D adult-animation satire, exaggerated faces, grotesque-cute or liminal weirdness — "
            "unless notes say otherwise; not corporate cyberpunk by default)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea (in-character)\n"
            "Keep it tight and actionable.\n"
        )
    else:
        prompt = (
            "You are a creative director for short-form vertical video (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Core angle / hook\n"
            "3) Beat-by-beat outline (6–10 beats for ~50 seconds total)\n"
            "4) Visual motifs (default high-contrast cyberpunk unless notes say otherwise)\n"
            "5) Short on-screen text keywords per beat\n"
            "6) Hashtag theme words (no # prefixes)\n"
            "7) CTA idea\n"
            "Keep it tight and actionable.\n"
        )
    with vram_guard():
        raw = _generate_with_transformers(
            model_id=model_id,
            prompt=prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=900,
            try_llm_4bit=try_llm_4bit,
        )
    return raw.strip()


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
    hashtags = ["#AI", "#Shorts", "#TechTok", "#Video", "#Creator", "#Storytelling", "#Tips", "#LearnOnTikTok"]
    for t in topic_tags or []:
        t2 = re.sub(r"[^A-Za-z0-9]+", "", (t or "").strip())
        if t2:
            hashtags.append("#" + t2[:28])
    hashtags = _normalize_hashtags(hashtags)[:30]
    segs = [
        ScriptSegment(
            narration=creative_brief[:320] + ("…" if len(creative_brief) > 320 else ""),
            visual_prompt="high-contrast cyberpunk cityscape, neon accents, vertical 9:16, cinematic",
            on_screen_text="HOOK",
        ),
        ScriptSegment(
            narration="Breaking it down: the key ideas from your brief, in plain language.",
            visual_prompt="clean cyberpunk infographic panels, glowing UI, 9:16, sharp contrast",
            on_screen_text="BREAKDOWN",
        ),
        ScriptSegment(
            narration="Why it lands: quick payoff for viewers who want clarity—not filler.",
            visual_prompt="neon timeline icons, futuristic HUD elements, 9:16",
            on_screen_text="WHY IT MATTERS",
        ),
        ScriptSegment(
            narration=f"Closing thought—keep it {personality.label.lower()} and actionable.",
            visual_prompt="close-up holographic interface, subtle glitch, 9:16",
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


def enforce_arc(pkg: VideoPackage) -> VideoPackage:
    """
    Best-effort post-processor to ensure the script includes context + why-it-matters beats.
    We don't require the model to label beats; we inject minimal beats if missing.
    """
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
                narration="Quick context: here’s what it is and what just changed.",
                visual_prompt="clean cyberpunk infographic panel, clear labels, high contrast, 9:16",
                on_screen_text="CONTEXT",
            )
        )
    if not has_why:
        insertions.append(
            ScriptSegment(
                narration="Why it matters: it saves time on a real workflow—if you use it the right way.",
                visual_prompt="cyberpunk timeline + impact icons, neon accents, high contrast, 9:16",
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

    # Keep overall beat count sane.
    out = out[: max(6, min(10, len(out)))]
    return VideoPackage(
        title=pkg.title,
        description=pkg.description,
        hashtags=list(pkg.hashtags),
        hook=pkg.hook,
        segments=out,
        cta=pkg.cta,
    )


def _emit_llm(
    on_llm_task: Callable[[str, int, str], None] | None, task: str, pct: int, msg: str
) -> None:
    if on_llm_task:
        on_llm_task(task, max(0, min(100, int(pct))), msg)


def torch_cuda_kernels_work() -> bool:
    """
    True only if basic CUDA tensor ops run on device 0.

    PyTorch wheels omit SASS for some newer (or unusual) GPUs; ``cuda.is_available()``
    can still be True while every kernel fails with "no kernel image is available".
    """
    import torch

    if not torch.cuda.is_available():
        return False
    try:
        x = torch.tensor([0, 1], device="cuda", dtype=torch.long)
        torch.isin(x, x)
        return True
    except RuntimeError:
        return False


def load_causal_lm_from_pretrained(
    load_path: str,
    *,
    try_4bit: bool = True,
    on_status: Callable[[str], None] | None = None,
) -> Any:
    """
    Load ``AutoModelForCausalLM`` from disk or Hub id.

    Tries bitsandbytes 4-bit first when ``try_4bit`` and CUDA works (saves VRAM).
    If 4-bit raises, falls back to fp16 with ``device_map="auto"``.

    If this PyTorch build has **no usable CUDA kernels** for the installed GPU
    (``cuda.is_available()`` true but ops fail with "no kernel image"), loads on
    **CPU** in fp16 — slower but runs on unsupported/new GPUs until you install a
    matching PyTorch build.
    """
    from .hf_transformers_imports import causal_lm_stack
    from .torch_dtypes import torch_float16

    AutoModelForCausalLM, _, BitsAndBytesConfig = causal_lm_stack()
    _fp16 = torch_float16()
    cuda_ok = torch_cuda_kernels_work()

    def _status(msg: str) -> None:
        if on_status:
            on_status(msg)

    def _from_pretrained_with_optional_bnb(
        *, quantization_config: Any | None, device_map: str
    ) -> Any:
        if quantization_config is not None:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    quantization_config=quantization_config,
                    device_map=device_map,
                    dtype=_fp16,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )
            except TypeError:
                try:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=_fp16,
                        low_cpu_mem_usage=True,
                        trust_remote_code=True,
                    )
                except TypeError:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=_fp16,
                        trust_remote_code=True,
                    )
        try:
            return AutoModelForCausalLM.from_pretrained(
                load_path,
                device_map=device_map,
                dtype=_fp16,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
            )
        except TypeError:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=_fp16,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )
            except TypeError:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=_fp16,
                    trust_remote_code=True,
                )

    if not cuda_ok:
        _status("CUDA unusable for this GPU/driver build; loading LLM on CPU (slower)…")
        return _from_pretrained_with_optional_bnb(quantization_config=None, device_map="cpu")

    if try_4bit:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=_fp16,
        )
        try:
            _status("Loading model (4-bit)…")
            return _from_pretrained_with_optional_bnb(quantization_config=bnb, device_map="auto")
        except Exception as e:
            _status(f"4-bit load failed ({type(e).__name__}); loading in fp16 instead…")
            return _from_pretrained_with_optional_bnb(quantization_config=None, device_map="auto")

    _status("Loading model (fp16)…")
    return _from_pretrained_with_optional_bnb(quantization_config=None, device_map="auto")


def _generate_with_transformers(
    model_id: str,
    prompt: str,
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 650,
    try_llm_4bit: bool = True,
) -> str:
    import torch

    from .hf_transformers_imports import causal_lm_stack, text_iterator_streamer_cls

    _, AutoTokenizer, _ = causal_lm_stack()

    def _stderr(msg: str) -> None:
        if not on_llm_task:
            import sys

            print(f"[Aquaduct] {msg}", file=sys.stderr, flush=True)

    def _load_status(detail: str) -> None:
        _emit_llm(on_llm_task, "llm_load", 55, detail)

    # Load from project `models/<repo>/` when present; plain repo id uses HF cache (extra downloads).
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_paths().models_dir)

    _emit_llm(on_llm_task, "llm_load", 0, "Loading tokenizer…")
    tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=True, trust_remote_code=True)
    _emit_llm(on_llm_task, "llm_load", 25, "Tokenizer ready")

    _emit_llm(on_llm_task, "llm_load", 30, "Loading model weights…")
    model = load_causal_lm_from_pretrained(
        load_path,
        try_4bit=bool(try_llm_4bit),
        on_status=_load_status,
    )
    _emit_llm(on_llm_task, "llm_load", 100, "Model loaded")

    # Simple chat-ish formatting without requiring tokenizer chat template support.
    full = f"### Instruction:\n{prompt}\n\n### Response:\n"
    inputs = tokenizer(full, return_tensors="pt").to(model.device)

    _emit_llm(on_llm_task, "llm_generate", 0, "Starting generation…")
    _stderr("LLM inference starting (streamed progress when supported).")
    dprint("brain", "generate() starting")

    raw_new: str | None = None

    try:
        from threading import Thread

        TextIteratorStreamer = text_iterator_streamer_cls()

        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": max_new_tokens,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
            "eos_token_id": tokenizer.eos_token_id,
        }

        def _run_gen() -> None:
            with torch.inference_mode():
                model.generate(**generation_kwargs)

        th = Thread(target=_run_gen, daemon=True)
        th.start()
        chunks: list[str] = []
        n_tok = 0
        for text in streamer:
            chunks.append(text)
            n_tok += 1
            pct = min(99, int(100 * n_tok / max(1, max_new_tokens)))
            _emit_llm(
                on_llm_task,
                "llm_generate",
                pct,
                f"Generating tokens ({n_tok}/{max_new_tokens})",
            )
        th.join(timeout=7200)
        raw_new = "".join(chunks)
        _emit_llm(on_llm_task, "llm_generate", 100, "Generation finished")
    except Exception as e:
        dprint("brain", "streamed generation failed, falling back", str(e))
        _emit_llm(on_llm_task, "llm_generate", 10, "Fallback: one-shot generate…")
        with torch.inference_mode():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.08,
                eos_token_id=tokenizer.eos_token_id,
            )
        _emit_llm(on_llm_task, "llm_generate", 100, "Decoding…")
        text_full = tokenizer.decode(out[0], skip_special_tokens=True)
        if "### Response:" in text_full:
            raw_new = text_full.split("### Response:", 1)[1].strip()
        else:
            raw_new = text_full

    assert raw_new is not None
    text = raw_new

    # Cleanup aggressively (VRAM limited)
    del model
    del tokenizer
    cleanup_vram()
    return text


def generate_script(
    *,
    model_id: str,
    items: list[dict[str, str]],
    topic_tags: list[str] | None = None,
    personality_id: str = "neutral",
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    creative_brief: str | None = None,
    video_format: str = "news",
    try_llm_4bit: bool = True,
) -> VideoPackage:
    """
    Generates a structured video package from scraped headlines/links, or from a pre-expanded custom creative brief.
    Tries local 4-bit transformers; falls back to a deterministic template if the model fails to load.
    """
    personality = get_personality_by_id(personality_id)
    if creative_brief is not None and str(creative_brief).strip():
        prompt = _prompt_for_creative_brief(
            expanded_brief=str(creative_brief),
            topic_tags=topic_tags,
            video_format=str(video_format or "news"),
            personality=personality,
            branding=branding,
            character_context=character_context,
        )
    else:
        prompt = _prompt_for_items(
            items,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            video_format=str(video_format or "news"),
        )
    mode = "custom_brief" if (creative_brief is not None and str(creative_brief).strip()) else "headlines"
    dprint("brain", "generate_script start", f"model_id={model_id!r}", f"mode={mode!r}", f"items={len(items)}", f"personality={personality_id!r}")

    with vram_guard():
        try:
            raw = _generate_with_transformers(
                model_id=model_id,
                prompt=prompt,
                on_llm_task=on_llm_task,
                try_llm_4bit=try_llm_4bit,
            )
            data = _extract_json(raw)
            pkg = _to_package(data)
            dprint("brain", "generate_script ok (transformers)", f"title={pkg.title[:100]!r}")
            return pkg
        except Exception:
            if creative_brief is not None and str(creative_brief).strip():
                pkg = _fallback_package_custom(
                    creative_brief=str(creative_brief),
                    items=items,
                    personality_id=personality_id,
                    topic_tags=topic_tags,
                    branding=branding,
                )
                dprint("brain", "generate_script ok (fallback custom)", f"title={pkg.title[:100]!r}")
                return pkg
            vf_fallback = str(video_format or "news").strip().lower()
            if vf_fallback == "unhinged":
                seed = (items[0].get("title") if items else "") or "Chaos hour"
                title = seed[:80]
                hook = "This headline showed up uninvited — we’re doing a full adult-animation meltdown."
                hashtags = [
                    "#AdultAnimation",
                    "#CartoonTok",
                    "#ComedyShorts",
                    "#Absurd",
                    "#Satire",
                    "#Animation",
                    "#Shorts",
                    "#Unhinged",
                    "#Parody",
                    "#Sketch",
                    "#Viral",
                    "#DarkComedy",
                    "#Toon",
                    "#Chaos",
                    "#Funny",
                    "#WTF",
                    "#Animated",
                ]
                pkg = VideoPackage(
                    title=title,
                    description=f"Adult-animation-style satire riff inspired by: {seed}",
                    hashtags=hashtags[:30],
                    hook=hook,
                    segments=[
                        ScriptSegment(
                            narration="Cold open: we pretend this is a normal news day — it is not. The vibe is wrong on purpose.",
                            visual_prompt="flat 2D adult cartoon, deadpan characters, liminal suburban background, 9:16",
                            on_screen_text="COLD OPEN",
                        ),
                        ScriptSegment(
                            narration="B-plot: the premise mutates into sci-fi sitcom chaos until someone yells about morality.",
                            visual_prompt="exaggerated TV-comedy staging, gross-out reaction shots, comic panels, speed lines, 9:16",
                            on_screen_text="ESCALATE",
                        ),
                        ScriptSegment(
                            narration="Tag: we stick the landing before the censors wake up. Subscribe if you’re still sane.",
                            visual_prompt="cartoon freeze-frame punchline, silly fireworks, 9:16",
                            on_screen_text="OUTRO",
                        ),
                    ],
                    cta="Follow for more unhinged adult cartoons.",
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
                                    visual_prompt=(
                                        s.visual_prompt if "Palette:" in s.visual_prompt else f"{s.visual_prompt}, {suf}"
                                    ),
                                    on_screen_text=s.on_screen_text,
                                )
                                for s in pkg.segments
                            ],
                            cta=pkg.cta,
                        )
                dprint("brain", "generate_script ok (fallback unhinged)", f"title={pkg.title[:100]!r}")
                return pkg
            # Fallback: minimal structured script without the LLM (keeps pipeline running).
            tool_title = (items[0].get("title") if items else "") or "New AI Tool"
            title = tool_title[:80]

            # Tone shaping for fallback
            if personality.id == "hype":
                hook = "Stop scrolling—this AI tool is actually insane."
                cta = "Follow for daily AI tool drops with real takeaways."
            elif personality.id == "analytical":
                hook = "Quick technical breakdown: a new AI tool just shipped."
                cta = "Follow for practical AI tooling breakdowns."
            elif personality.id == "comedic":
                hook = "Stop scrolling—your workflow is about to get bullied (in a good way)."
                cta = "Follow for daily AI tools, minus the cringe."
            elif personality.id == "skeptical":
                hook = "Before you believe the hype—here’s what this new AI tool really does."
                cta = "Follow for honest AI tool reviews and trade-offs."
            elif personality.id == "cozy":
                hook = "Hey—quick and simple: this new AI tool might save you time."
                cta = "Follow for friendly AI tool tips you can use today."
            elif personality.id == "urgent":
                hook = "Breaking: a new AI tool just dropped—here’s the fast rundown."
                cta = "Follow for daily AI news you can act on."
            elif personality.id == "contrarian":
                hook = "Hot take: this new AI tool is useful—but not for the reason you think."
                cta = "Follow for sharp AI tool takes with receipts."
            else:
                hook = "Stop scrolling—this new AI tool just dropped."
                cta = "Follow for daily AI tool reviews you can actually use."

            pkg = VideoPackage(
                title=title,
                description=f"Fast review: {tool_title}. What it does, who it’s for, and why it matters.",
                hashtags=[
                    "#AI",
                    "#AITools",
                    "#AInews",
                    "#Productivity",
                    "#TechTok",
                    "#Automation",
                    "#MachineLearning",
                    "#Startup",
                    "#NewApp",
                    "#ToolReview",
                    "#Cyberpunk",
                    "#FutureTech",
                    "#Tech",
                    "#Shorts",
                    "#TikTok",
                ],
                hook=hook,
                segments=[
                    ScriptSegment(
                        narration=f"Today’s drop: {tool_title}. Here’s the quick breakdown.",
                        visual_prompt="high-contrast cyberpunk city, neon UI overlay, holographic app panels, sharp, cinematic, 9:16",
                        on_screen_text="NEW TOOL DROP",
                    ),
                    ScriptSegment(
                        narration="What it does: it automates a boring workflow in seconds.",
                        visual_prompt="neon cyberpunk dashboard, glowing graphs, crisp UI, dark background, 9:16, high contrast",
                        on_screen_text="WHAT IT DOES",
                    ),
                    ScriptSegment(
                        narration="Who it’s for: creators, builders, and anyone who wants speed.",
                        visual_prompt="cyberpunk creator desk, neon lighting, holograms, tech aesthetic, 9:16",
                        on_screen_text="WHO IT’S FOR",
                    ),
                    ScriptSegment(
                        narration="My take: test it on one task today and keep the best results.",
                        visual_prompt="close-up neon terminal, glitch effect, futuristic UI, 9:16, sharp",
                        on_screen_text="QUICK TAKE",
                    ),
                ],
                cta=cta,
            )

            # Apply palette to fallback prompts (best-effort)
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
            # If tags are provided, append a couple as hashtags (best-effort).
            if topic_tags:
                extra = []
                for t in topic_tags:
                    t = re.sub(r"[^A-Za-z0-9]+", "", (t or "").strip())
                    if t:
                        extra.append("#" + t[:28])
                pkg = VideoPackage(
                    title=pkg.title,
                    description=pkg.description,
                    hashtags=(pkg.hashtags + extra)[:30],
                    hook=pkg.hook,
                    segments=pkg.segments,
                    cta=pkg.cta,
                )
            dprint("brain", "generate_script ok (fallback template)", f"title={pkg.title[:100]!r}")
            return pkg


def generate_character_from_preset_llm(
    *,
    model_id: str,
    preset: CharacterAutoPreset,
    extra_notes: str = "",
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 1400,
    try_llm_4bit: bool = True,
) -> GeneratedCharacterFields:
    """
    Use the script LLM to invent a full character profile (text fields) from a built-in archetype.
    Does not assign pyttsx3 / ElevenLabs IDs — user picks voices in the UI.
    """
    from .characters_store import CHARACTER_FIELD_MAX_LEN, CHARACTER_NAME_MAX_LEN

    notes = (extra_notes or "").strip()
    notes_block = f"Extra notes from the user (optional):\n{notes}\n" if notes else ""

    arch = (preset.llm_directive or "").strip() or "Original short-form video host."
    prompt = (
        "You help users of a desktop short-form video app (9:16 vertical).\n"
        "Invent ONE original host character — not a real celebrity, brand mascot, or copyrighted figure.\n\n"
        f"Archetype label: {preset.label}\n"
        f"Creative direction for this archetype:\n{arch}\n\n"
        f"{notes_block}"
        "Output a single JSON object with EXACTLY these keys:\n"
        '- "name": short memorable display name (string)\n'
        '- "identity": persona for script + on-screen context — tone, audience, how they talk (string, several sentences)\n'
        '- "visual_style": string to prepend to image prompts — look, lighting, wardrobe, set (several short sentences)\n'
        '- "negatives": comma-separated diffusion negative prompts to reduce artifacts (string)\n'
        '- "use_default_voice": boolean — true if a generic project TTS is fine; false if the character needs a distinct voice pick\n'
        "\n"
        "Rules:\n"
        "- Output ONLY valid JSON. No markdown fences, no commentary before or after.\n"
        "- Do not include keys other than the five above.\n"
        "- Keep everything original; no real-person imitation.\n"
    )
    with vram_guard():
        raw = _generate_with_transformers(
            model_id,
            prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            try_llm_4bit=try_llm_4bit,
        )
    blob = extract_first_json_object(raw or "")
    coerced = coerce_generated_character_fields(blob)
    if coerced is None:
        raise ValueError("Model did not return usable JSON with name, identity, and visual fields.")
    return GeneratedCharacterFields(
        name=coerced.name[:CHARACTER_NAME_MAX_LEN],
        identity=coerced.identity[:CHARACTER_FIELD_MAX_LEN],
        visual_style=coerced.visual_style[:CHARACTER_FIELD_MAX_LEN],
        negatives=coerced.negatives[:CHARACTER_FIELD_MAX_LEN],
        use_default_voice=coerced.use_default_voice,
    )


def expand_custom_field_text(
    *,
    model_id: str,
    field_label: str,
    seed: str,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 512,
    try_llm_4bit: bool = True,
) -> str:
    """
    Use the local LLM to expand or improve free-form UI text (character fields, topics, prompts, etc.).
    """
    fl = (field_label or "text field").strip() or "text field"
    seed_stripped = (seed or "").strip()
    if not seed_stripped:
        user_part = (
            "The user has not written anything yet. Invent concise, usable starter text appropriate for this field."
        )
    else:
        user_part = f"The user's notes or draft:\n---\n{seed_stripped}\n---"
    prompt = (
        f"You help users of a desktop video production app. Improve or expand text for the field «{fl}».\n\n"
        f"{user_part}\n\n"
        "Rules:\n"
        "- Output ONLY the final text for that field.\n"
        "- No preamble, title line, or explanation.\n"
        "- No markdown code fences.\n"
        "- Match the expected style: short for tags/negatives; richer for persona/visual prompts.\n"
    )
    with vram_guard():
        raw = _generate_with_transformers(
            model_id,
            prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            try_llm_4bit=try_llm_4bit,
        )
    out = (raw or "").strip()
    # Trim common wrappers
    if out.startswith("```"):
        lines = out.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        out = "\n".join(lines).strip()
    if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
        out = out[1:-1].strip()
    return out

