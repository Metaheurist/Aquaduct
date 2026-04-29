from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.util.utils_vram import cleanup_vram, vram_guard
from .personalities import PersonalityPreset, get_personality_by_id
from .character_presets import (
    CharacterAutoPreset,
    GeneratedCharacterFields,
    coerce_generated_character_fields,
    extract_first_json_object,
)
from src.core.config import AppSettings, ARTICLE_EXCERPT_MAX_CHARS, BrandingSettings, get_paths
from src.core.models_dir import get_models_dir
from src.models.model_manager import resolve_pretrained_load_path
from src.render.branding_video import palette_prompt_suffix, video_style_strength
from debug import dprint

# Spoken script targets for preset + custom brief paths (longer, data-rich shorts)
_SCRIPT_RUNTIME = "roughly 75–95 seconds of spoken narration at a brisk pace"
_SCRIPT_SEGMENTS = "10–16"
_SCRIPT_WORDS = "approximately 240–320 words total across hook + segment narrations + CTA"


def clip_article_excerpt(text: str | None, *, max_chars: int | None = None) -> str:
    """Trim article body for LLM prompts; empty if no text."""
    cap = max_chars if max_chars is not None else ARTICLE_EXCERPT_MAX_CHARS
    t = (text or "").strip()
    if not t:
        return ""
    return t[:cap]


def _article_prompt_block(*, video_format: str, excerpt: str) -> str:
    ex = (excerpt or "").strip()
    if not ex:
        return ""
    vf = (video_format or "news").strip().lower()
    if vf in ("cartoon", "unhinged"):
        return (
            "Optional article text (use for proper nouns, numbers, or extra context — do not turn the video into a dry news recap):\n"
            f"{ex}\n\n"
        )
    if vf == "creepypasta":
        return (
            "Scraped story text (fiction — adapt freely into an original short script; do not claim real events or real people):\n"
            f"{ex}\n\n"
        )
    if vf == "explainer":
        return (
            "Article excerpt (ground truth for definitions, facts, numbers, names, and quotes — prefer these over guessing; "
            "if the excerpt is silent, say you are unsure or stay vague):\n"
            f"{ex}\n\n"
        )
    if vf == "health_advice":
        return (
            "Article excerpt (ground truth for general wellness facts, definitions, and public-health-style information — "
            "prefer these over guessing; hedge or stay vague where sources disagree; "
            "do not diagnose the viewer or tell them to start, stop, or change medication or treatment):\n"
            f"{ex}\n\n"
        )
    return (
        "Article excerpt (ground truth for facts, names, numbers, and quotes — prefer these over guessing):\n"
        f"{ex}\n\n"
    )


_TTS_SPOKEN_RULES = (
    "Text-to-speech rules (mandatory):\n"
    "- `hook`, each segment `narration`, and `cta` are read aloud by TTS. Put ONLY speakable words there: host/character "
    "dialogue, or first-person lines meant to be heard.\n"
    "- Do NOT put stage directions, camera notes, editing cues, or parenthetical actions in those fields "
    "(no “(beat)”, “we cut to”, “zoom in”, “[music swells]”, “B-roll:”, “voice-over:”). "
    "All staging, camera, lighting, and scene description belong ONLY in `visual_prompt` (image generation; not spoken).\n"
    "- Keep `on_screen_text` to short captions or labels for graphics, not narration.\n\n"
)

_VINE_MEME_STRUCTURE = (
    "Pacing: meme-comic / classic short-form (Vine-style) energy — rapid beats, setup→punch→reaction, quotable lines; "
    "each segment should feel like the next panel or next cut.\n\n"
)

# Keeps small LLMs from echoing generic Shorts scaffolding instead of real story beats.
_SCRIPT_SUBSTANCE_RULES = (
    "Quality bar (mandatory):\n"
    "- Every beat must add **new** substance: a fact, name, number, stake, or a joke tied to the sources — not empty hype.\n"
    "- **Do not** lean on these clichés (or close paraphrases) as whole sentences or repeated transitions: "
    "\"here's the rundown\", \"here's what you need to know\", \"one of the\", \"quick context\", "
    "\"here's why this matters\", \"here's what's actually going on\", \"key takeaway\", \"according to early reports\", "
    "\"keep an eye on updates\", \"who this hits hardest\", \"my read\", \"watch what happens next\", "
    "\"the part that actually matters\", \"this headline\", \"walked in like it owned\", \"nobody agreed\", "
    "\"we escalated\", \"yelled about morality\", \"stick the landing\", \"before the bit gets old\", \"still sane\".\n"
    "- If a headline is broken English, SEO spam, or a mangled listicle title, **state the topic in clean plain language** "
    "— do not read gibberish aloud or repeat the same broken phrase every segment.\n"
    "- `visual_prompt` must show **this beat's** main subject + setting + one clear action (readable silhouette, one focal idea, 9:16). "
    "Avoid prompts that are only \"dynamic graphics\" / \"bold text\" with no concrete scene.\n\n"
)

_SCRIPT_SUBSTANCE_RULES_COMEDY_EXTRA = (
    "Comedy-only: meta jokes about \"shorts\", \"the algorithm\", or \"the headline\" are ok **once** if they punch a specific source; "
    "the rest should be character story with real callbacks to the tags/headlines.\n\n"
)


def _horror_visual_prompt_rules(*, video_format: str) -> str:
    """Diffusion guidance for creepypasta — atmospheric dread, not gore porn or readable text walls."""
    vf = (video_format or "news").strip().lower()
    if vf != "creepypasta":
        return ""
    return (
        "`visual_prompt` rules (still image per beat — mandatory):\n"
        "- **Figurative horror scenes**: silhouettes, shadows, one focal threat or uncanny detail — "
        "not splatter, not photoreal injury, not sexual violence.\n"
        "- Prefer **implied dread**: fog, grain, wrong lighting, liminal hallways, empty rooms, moonlit windows, "
        "vintage flash photo, analog glitch, candlelit faces (no readable signage or long text).\n"
        "- Each `visual_prompt` must **match that segment's narration** mood — not a random sci-fi corridor.\n\n"
    )


def _health_visual_prompt_rules(*, video_format: str) -> str:
    vf = (video_format or "news").strip().lower()
    if vf != "health_advice":
        return ""
    return (
        "`visual_prompt` rules (still image per beat — mandatory):\n"
        "- **Medical-education tone**: trusted clinician figure (original character, not a real celebrity), soft clinic or "
        "clean teaching space, diagrams, anatomical **illustrations** (stylized, not photoreal gore or injury).\n"
        "- No readable long text, no graphic wounds, no sexualized medical imagery.\n"
        "- Each `visual_prompt` must **match that segment's narration** — calm, clear, reassuring composition, 9:16.\n\n"
    )


def _meme_visual_prompt_rules(*, video_format: str) -> str:
    """Extra diffusion guidance for cartoon/unhinged — reduces generic neon/abstract stills."""
    vf = (video_format or "news").strip().lower()
    if vf == "creepypasta":
        return _horror_visual_prompt_rules(video_format=vf)
    if vf == "health_advice":
        return _health_visual_prompt_rules(video_format=vf)
    if vf not in ("cartoon", "unhinged"):
        return ""
    return (
        "`visual_prompt` rules (still image per beat — mandatory):\n"
        "- **Figurative scenes only**: named characters from the cast, concrete props, and one readable joke or reaction tableau — "
        "not abstract neon car wheels, empty cyberpunk corridors, generic \"holographic UI\", or unrelated sci-fi spectacle "
        "unless that beat's narration is literally about that object.\n"
        "- For internet-meme / brainrot / shitpost topics: lean **chaotic Shorts meme** look — thick black outlines, flat loud colors, "
        "wrong perspective on purpose, crowded backgrounds, surreal proportions (the \"Italian brainrot\" collage energy: absurd mashups, "
        "expressive faces, meme objects).\n"
        "- Each `visual_prompt` must **match that segment's narration**, not a random pretty background.\n\n"
    )


def _tts_block() -> str:
    return _TTS_SPOKEN_RULES


def _character_voice_block(character_context: str | None, *, video_format: str) -> str:
    vf = (video_format or "news").strip().lower()
    cc = (character_context or "").strip()
    if cc:
        if vf in ("cartoon", "unhinged"):
            return (
                "Character / cast (mandatory — all spoken lines are these voices):\n"
                f"{cc}\n\n"
            )
        if vf == "creepypasta":
            return (
                "Narrator (mandatory — the entire spoken script is this voice; first-person past tense unless the block says otherwise):\n"
                f"{cc}\n\n"
            )
        if vf == "health_advice":
            return (
                "Clinician (mandatory — the entire spoken script is this doctor or nurse persona; educational, not alarmist):\n"
                f"{cc}\n\n"
            )
        return (
            "Character / host (mandatory — the entire spoken script is this persona; not a generic anonymous announcer):\n"
            f"{cc}\n\n"
        )
    if vf in ("cartoon", "unhinged"):
        return (
            "Character / cast: none provided — invent 1–3 original characters (names + voices) that fit the topic_tags and "
            "headlines. Spoken fields = dialogue or in-character lines only.\n\n"
        )
    if vf == "creepypasta":
        return (
            "Narrator: none provided — invent one first-person campfire narrator (name + voice) aligned with the topic_tags and "
            "sources; the hook must feel personally uneasy, not like a TV promo.\n\n"
        )
    if vf == "explainer":
        return (
            "Host: none provided — invent one explainer host (name + voice) aligned with the topic_tags and headlines.\n\n"
        )
    if vf == "health_advice":
        return (
            "Clinician: none provided — invent **one** original doctor **or** nurse (name + voice, generic medical professional — "
            "not a real person or celebrity). The entire spoken script is this persona: warm, clear, educational; "
            "first-person or direct address as a clinician on a wellness short.\n\n"
        )
    return (
        "Host: none provided — invent one host persona (name + voice) aligned with the topic_tags and headlines; "
        "the hook must react to those stories (do not assume a topic unless the tags or sources support it).\n\n"
    )


def _personality_character_fusion_block(
    personality: PersonalityPreset,
    character_context: str | None,
    *,
    video_format: str,
) -> str:
    """
    Explicit instruction to compose character identity with personality-driven delivery (not two disconnected blocks).
    """
    cc = (character_context or "").strip()
    vf = (video_format or "news").strip().lower()
    who_hint = "the named host or cast in the character block"
    if cc:
        first = cc.splitlines()[0].strip()
        if first:
            who_hint = first[:160] + ("…" if len(first) > 160 else "")

    beat_note = ""
    if vf in ("cartoon", "unhinged"):
        if personality.id == "comedic":
            beat_note = (
                "Meme/Vine beat density: favor more punchlines per minute and quicker joke turns; keep quotable lines.\n"
            )
        elif personality.id == "analytical":
            beat_note = (
                "Meme/Vine beat density: fewer throwaway gags—prioritize clear setup→payoff and one strong idea per beat.\n"
            )
        else:
            beat_note = (
                "Meme/Vine beat density: match punchline frequency to this tone (playful tones: more gags; skeptical/analytical: fewer, sharper jokes).\n"
            )
    elif vf == "creepypasta":
        beat_note = (
            "Horror pacing: favor concrete wrong details and callbacks over loud hype; let dread accumulate beat-to-beat.\n"
        )
    elif vf == "health_advice":
        beat_note = (
            "Health-education pacing: one clear idea per beat; favor reassurance, hedging, and \"check with your clinician\" "
            "where individual care applies — never prescribe or diagnose the viewer.\n"
        )

    return (
        "Tone + character together (mandatory):\n"
        f"- Keep **who** is speaking consistent with the character/cast block ({who_hint}).\n"
        f"- Let **{personality.label}** shape **how** they speak—rhythm, joke density, skepticism vs hype—using the Tone/personality style rules and Do/Don't above.\n"
        "- Do not replace the character with a generic announcer; do not let tone jokes erase factual anchors the character would still care about.\n"
        f"{beat_note}"
        "\n"
    )


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
            if narration and visual:
                segments.append(ScriptSegment(narration=narration, visual_prompt=visual, on_screen_text=on_screen_text))

    if not segments:
        # Minimal fallback structure
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


def video_package_from_llm_output(text: str) -> VideoPackage:
    """Parse model output (JSON, possibly fenced) into a VideoPackage."""
    return _to_package(_extract_json(text))


def _supplement_context_block(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    cap = 12_000
    if len(t) > cap:
        t = t[: cap - 1] + "…"
    return (
        "Supplemental research / web context (may include search synthesis; verify facts against the article excerpt when present):\n"
        f"{t}\n\n"
    )


def _prompt_for_unhinged_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    *,
    article_excerpt: str = "",
    video_format: str = "unhinged",
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
    char_block = _character_voice_block(character_context, video_format=video_format)
    fusion = _personality_character_fusion_block(
        personality, character_context, video_format=video_format
    )
    art = _article_prompt_block(video_format=video_format, excerpt=article_excerpt)
    return (
        "You are a comedy writer for chaotic vertical shorts (9:16). Write an UNHINGED CARTOON script in the spirit of "
        "prestige adult-animation comedy: absurdist dread and awkward pauses, cynical sci-fi or family-sitcom banter, "
        "shock-satire punchlines, grotesque-cute or liminal-weird imagery — like classic adult animated sitcoms, "
        "NOT kids' TV or product reviews. Do not name, quote, or imitate any real show, character, or creator; "
        "invent original voices and settings. Stay playful; no slurs, hate, harassment, or real-person cruelty.\n"
        f"{_VINE_MEME_STRUCTURE}"
        "Drive the story from the **topic tags**, **headlines**, and **character** below — not from a fixed genre like “tech news”. "
        "Weave **at least 2–4** distinct headlines or angles into one coherent satirical arc. "
        "Name the outlet/source when it sharpens the joke. Twist or parody freely; this is NOT a neutral news report and NOT a tutorial.\n"
        "Storytelling rule: The `hook` and every segment's `narration` must be in character voice — "
        "first-person, dialogue between characters, or close third tied to a named character. "
        "Do NOT default to a neutral news announcer; the story is told through the cast.\n"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_SCRIPT_SUBSTANCE_RULES_COMEDY_EXTRA}"
        f"{_tts_block()}"
        f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats. Each beat should feel snappy and quotable "
        "(deadpan or manic energy both work).\n"
        "Visual style: exaggerated 2D adult-animation look — flat color, rubber-hose or sharp TV-comedy staging, "
        "gross-out or surreal backgrounds when it sells the joke — NOT corporate cyberpunk unless the joke demands it.\n"
        f"{_meme_visual_prompt_rules(video_format=video_format)}"
        "Enforce this arc (adapt timing across segments):\n"
        "- Hook: wrong-foot the viewer — fake-wholesome, deadpan doom, or sudden satire\n"
        "- Escalation: the premise spirals (sitcom argument, sci-fi nonsense, or moral panic)\n"
        "- Chaos peak: maximum cartoon transgression with one concrete visual gag per beat where possible\n"
        "- Payoff: land the joke (bleeped energy ok in text; no real slurs)\n"
        "- Close/CTA: ironic follow / subscribe bit\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items from the actual topics and tone (comedy, satire, animation, viral — match the story, not a default niche)\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        f"{art}"
        f"Headlines (each has title, url, source, published_at when known — use several): "
        f"{json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_creepypasta_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    *,
    article_excerpt: str = "",
    video_format: str = "creepypasta",
) -> str:
    """Preset: fictional horror shorts adapted from online creepypasta / short scary fiction pages."""
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = f"Topic tags (bias mood, setting, and hashtags): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
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
    char_block = _character_voice_block(character_context, video_format=video_format)
    fusion = _personality_character_fusion_block(
        personality, character_context, video_format=video_format
    )
    art = _article_prompt_block(video_format=video_format, excerpt=article_excerpt)
    return (
        "You are a horror fiction writer for vertical creepypasta shorts (9:16). "
        "Sources below are **titles + URLs + scraped text** from the open web (reddit threads, blogs, fiction sites). "
        "Treat them as **inspiration for wholly original fiction** — paraphrase, rename, relocate; do not claim true events, "
        "real missing persons, or real crimes. No slurs, hate, sexual violence, or glorification of self-harm. "
        "Keep dread **atmospheric** (implied threat, wrong details, silence) — avoid graphic gore walkthroughs.\n"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_tts_block()}"
        f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
        "The `hook` must grab with unease tied to the real source titles or tags — not a generic “story time” opener.\n"
        "Weave **at least 2–4** distinct source angles or motifs into one arc (echoes, false endings, callbacks).\n"
        "Default voice: **first-person past-tense campfire narrator** (or tight third-person if character block demands) — "
        "not a peppy news host.\n"
        f"{_meme_visual_prompt_rules(video_format=video_format)}"
        "Enforce this arc (adapt timing across segments):\n"
        "- Hook: wrong detail, too-quiet setup, or a rule that should not exist\n"
        "- Rising dread: escalate through clues, repetition, or uncanny behavior\n"
        "- Twist / reveal: one clean fictional punch (not a documentary conclusion)\n"
        "- Aftershock: one beat of lingering wrongness\n"
        "- Close/CTA: low-key unsettling sign-off (still speakable)\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items (horror fiction, creepypasta, scary shorts, urban legend — match the story)\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        f"{art}"
        f"Sources (title, url, source — use several): {json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_cartoon_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    *,
    article_excerpt: str = "",
    video_format: str = "cartoon",
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
    char_block = _character_voice_block(character_context, video_format=video_format)
    fusion = _personality_character_fusion_block(
        personality, character_context, video_format=video_format
    )
    art = _article_prompt_block(video_format=video_format, excerpt=article_excerpt)
    return (
        "You are a comedy writer for playful cartoon vertical shorts (9:16) — think meme comic panels meets classic short-form video: "
        "fast setup, punchline, reaction; clear beginning, middle, and payoff.\n"
        f"{_VINE_MEME_STRUCTURE}"
        "Drive jokes and story beats from the **topic tags**, **headlines**, and **characters** below (not a fixed genre). "
        "Headlines may be animation/cartoon buzz, internet culture, or whatever the user’s topics surfaced — weave **at least 2–3** "
        "into one arc (callbacks, rival stories, running gags). Parody or twist freely. "
        "Do NOT write a tutorial or step-by-step lesson unless the user data clearly asks for it.\n"
        "Storytelling rule: The `hook` and every segment's `narration` must be in character voice — "
        "first-person, dialogue between characters, or close third tied to a named character. "
        "Do NOT use a neutral TV announcer or product-demo narrator unless the joke is explicitly about that.\n"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_SCRIPT_SUBSTANCE_RULES_COMEDY_EXTRA}"
        f"{_tts_block()}"
        f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats. Keep language family-friendly; no slurs or hate.\n"
        "Visual style: bright 2D cartoon, bold shapes, expressive faces, rubber-hose or modern toon energy — all visual jokes/staging go in `visual_prompt`.\n"
        f"{_meme_visual_prompt_rules(video_format=video_format)}"
        "Enforce this arc (adapt timing across segments):\n"
        "- Hook: wrong-foot or playful chaos (instant premise)\n"
        "- Rising action: escalate, argue, chase the idea\n"
        "- Peak: biggest gag\n"
        "- Payoff: land the joke from the cast's POV\n"
        "- Close/CTA: in-character sign-off\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Use `on_screen_text` for short dialogue tags, reactions, or caption jokes.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items drawn from the real topics and tone (cartoon, comedy, shorts — match the story)\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        f"{art}"
        f"Headlines (each has title, url, source, published_at when known — use several): "
        f"{json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_health_advice_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    article_excerpt: str = "",
    *,
    video_format: str = "health_advice",
) -> str:
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    tag_line = (
        f"Topic tags (bias wellness angles and on-screen hashtags): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
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
    vf = "health_advice"
    char_block = _character_voice_block(character_context, video_format=vf)
    fusion = _personality_character_fusion_block(personality, character_context, video_format=vf)
    art = _article_prompt_block(video_format=vf, excerpt=article_excerpt)
    safety = (
        "Medical safety (mandatory):\n"
        "- This is **general wellness education** for entertainment — **not** personal medical advice, diagnosis, or treatment planning.\n"
        "- Do **not** tell viewers to start, stop, or change medication, supplements, or therapy. Do **not** diagnose the viewer from symptoms.\n"
        "- Encourage seeing a qualified clinician for personal concerns, red-flag symptoms, or before major lifestyle changes.\n"
        "- Hedge uncertain claims; prefer language like \"research suggests\", \"many guidelines recommend\", \"talk to your care team\".\n"
        "- No graphic descriptions of injury, surgery, or self-harm.\n\n"
    )
    role = (
        "You write short-form **health education** vertical video (9:16) scripts voiced by **one** original doctor or nurse character "
        "(see character block). Build the arc from the **topic tags**, **headlines**, and **article excerpt** — wellness tips, "
        "lifestyle habits, and **general** facts about conditions (public-health style), not sensational cures.\n"
        "Weave **at least 2–4** headline angles or sources into one coherent narrative where possible.\n"
    )
    structure = (
        f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
        "The `hook` must come from the actual topics and headlines. Deliver everything **in the clinician’s voice** "
        "(first person or caring direct address).\n"
        "Enforce this arc (adapt timing across segments):\n"
        "- Hook: relatable wellness question or myth — framed carefully (no fear-mongering)\n"
        "- Context: what the topic is in plain language\n"
        "- Tips / facts: concrete, evidence-leaning beats (from excerpt/headlines when present)\n"
        "- Conditions / self-care: general education only — no individualized treatment instructions\n"
        "- Close/CTA: include a brief disclaimer that this is not medical advice + encourage professional care + follow/subscribe in character\n"
    )
    extra_rules = (
        "- Include **one** spoken line (hook, segment, or CTA) that clearly states the video is educational and not a substitute for professional care.\n"
        "- `visual_prompt`: clinician-led teaching moments, diagrams, or calm exam-room staging — see visual rules below.\n"
    )
    return (
        f"{safety}"
        f"{role}"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_tts_block()}"
        f"{structure}"
        f"{_health_visual_prompt_rules(video_format=vf)}"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items; wellness, education, shorts — match the topics\n"
        f"{extra_rules}"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        f"{art}"
        f"Headlines (each has title, url, source, published_at when known — use several): "
        f"{json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _prompt_for_items(
    headlines: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    video_format: str = "news",
    article_excerpt: str = "",
) -> str:
    vf = (video_format or "news").strip().lower()
    if vf == "cartoon":
        return _prompt_for_cartoon_items(
            headlines,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=article_excerpt,
            video_format=vf,
        )
    if vf == "unhinged":
        return _prompt_for_unhinged_items(
            headlines,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=article_excerpt,
            video_format=vf,
        )
    if vf == "creepypasta":
        return _prompt_for_creepypasta_items(
            headlines,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=article_excerpt,
            video_format=vf,
        )
    if vf == "health_advice":
        return _prompt_for_health_advice_items(
            headlines,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=article_excerpt,
            video_format=vf,
        )
    # Keep it stable for JSON parsing.
    tags = [t.strip() for t in (topic_tags or []) if t and t.strip()]
    if vf == "explainer":
        tag_line = f"Topic tags (bias the explanation angle and on-screen hashtags): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
    else:
        tag_line = f"Topic tags (must strongly influence the story angle and hashtags): {json.dumps(tags, ensure_ascii=False)}\n" if tags else ""
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
    char_block = _character_voice_block(character_context, video_format=vf)
    fusion = _personality_character_fusion_block(personality, character_context, video_format=vf)
    art = _article_prompt_block(video_format=vf, excerpt=article_excerpt)
    if vf == "explainer":
        role = (
            "You are a sharp explainer for vertical video (9:16). Build the script **only** from the topic tags, headlines, "
            "character/host, and article excerpt below — do not default to any single domain (e.g. do not assume AI/tech unless those tags or sources say so).\n"
            "When an article excerpt is present, ground specifics (numbers, names, quotes) in it; do not invent beyond it.\n"
            "Weave **at least 2–4** headlines or angles into one arc — contrast outlets, sequence cause→effect, or show how stories connect.\n"
            "Teach something concrete: by the end, the viewer should know **what** the thing is, **who** it affects, and **one** decision rule or trade-off — not a string of empty transitions.\n"
        )
        structure = (
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
            "The `hook` must be generated from the actual topics and headlines (not a generic opener). "
            "Style: punchy, precise. Default visuals: bold, readable, modern vertical-short graphics unless the topic demands otherwise — describe visuals only in `visual_prompt`.\n"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: what viewers will learn — delivered **in host voice** (character above)\n"
            "- Context: what happened / what the thing is (plain words)\n"
            "- Breakdown: concrete beats — mechanisms, stakeholders, numbers, timelines\n"
            "- Trade-offs or debate: risks, limits, who wins or loses\n"
            "- Close/CTA: short follow/subscribe line in host voice\n"
        )
        extra_rules = "- surface at least one concrete number, date, or named entity from the excerpt or headlines when available\n"
    else:
        role = (
            "You are a short-form host for vertical video (9:16). The script must be driven by the **topic tags**, **headlines**, "
            "and **character** below — not by a default genre. Do **not** assume AI, tech, or any topic unless the tags or headlines support it.\n"
            "Weave **at least 2–4** headlines into one coherent arc — compare takes, stitch a timeline, or contrast outlets. "
            "Name the source or outlet when it helps. Use the article excerpt for facts and quotes when present.\n"
        )
        structure = (
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
            "The `hook` must react to the actual story material above. Deliver the whole thing **in the host character’s voice** "
            "(first person or direct address), not as a bland anonymous anchor.\n"
            "Style: punchy, factual where appropriate. Visual look belongs in `visual_prompt` only.\n"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: one punchy line tied to the real headlines/topics\n"
            "- Context: what happened / what’s new\n"
            "- Key points: several concrete beats\n"
            "- Why it matters: who should care\n"
            "- Close/CTA: short sign-off in character\n"
        )
        extra_rules = "- name the main people, places, products, or events from the sources when relevant (do not invent names)\n"
    return (
        f"{role}"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_tts_block()}"
        f"{structure}"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items; prioritize topic_tags and the subject matter of the headlines\n"
        f"{extra_rules}"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        f"{art}"
        f"Headlines (each has title, url, source, published_at when known): "
        f"{json.dumps(headlines, ensure_ascii=False)}\n"
    )


def _vf_hint(video_format: str) -> str:
    f = (video_format or "news").strip().lower()
    if f in ("news", "explainer"):
        return "timely, host-in-character; driven by user topics and headlines (any subject domain)"
    if f == "cartoon":
        return (
            "character-driven cartoon comedy; meme/Vine-style pacing; topics and headlines set the subject — "
            "entertainment-first; not a dry tutorial unless the user asked"
        )
    if f == "unhinged":
        return (
            "adult-animation comedy satire from internet/viral material — absurdist, cynical banter, shock-cartoon punchlines; "
            "original characters; playful only"
        )
    if f == "creepypasta":
        return (
            "fictional horror short for vertical video — campfire / urban-legend tone from online creepypasta sources; "
            "single narrator or tight POV; atmospheric dread, no real-person harm claims"
        )
    if f == "health_advice":
        return (
            "clinician-voiced wellness education for vertical video — general tips and condition overviews from web sources; "
            "hedged, non-alarmist, not personal medical advice"
        )
    return "timely angle anchored to user topics and sources"


def _prompt_for_creative_brief(
    *,
    expanded_brief: str,
    topic_tags: list[str] | None,
    video_format: str,
    personality: PersonalityPreset,
    branding: BrandingSettings | None = None,
    character_context: str | None = None,
    article_excerpt: str = "",
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
    char_block = _character_voice_block(character_context, video_format=str(video_format or "news"))
    fusion = _personality_character_fusion_block(
        personality, character_context, video_format=str(video_format or "news")
    )
    vf = _vf_hint(video_format)
    vf_key = (video_format or "news").strip().lower()
    art = _article_prompt_block(video_format=vf_key, excerpt=article_excerpt)
    if vf_key == "cartoon":
        return (
            "You are a comedy writer for cartoon vertical shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            f"{_VINE_MEME_STRUCTURE}"
            "Narration must be in character voice throughout (dialogue or first-person), not a detached announcer.\n"
            "Default visual style: bright 2D cartoon, expressive acting — unless the brief says otherwise.\n"
            f"{_meme_visual_prompt_rules(video_format=vf_key)}"
            f"{_SCRIPT_SUBSTANCE_RULES}"
            f"{_SCRIPT_SUBSTANCE_RULES_COMEDY_EXTRA}"
            f"{_tts_block()}"
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: a character opens\n"
            "- Rising action: cast drives the story\n"
            "- Peak: biggest gag\n"
            "- Payoff + CTA: in-character close\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            f"- narration total {_SCRIPT_WORDS}\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items matching the brief’s topics and tone\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{fusion}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
            f"{art}"
        )
    if vf_key == "unhinged":
        return (
            "You are a comedy writer for adult-animation-style vertical shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            f"{_VINE_MEME_STRUCTURE}"
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats. "
            "Do not name or imitate real shows or characters; invent originals.\n"
            "Narration must be in character voice throughout — not a neutral news announcer.\n"
            "Default visual style: flat 2D adult-animation satire, exaggerated acting, gross-out or surreal sets — "
            "unless the brief says otherwise (not corporate cyberpunk by default).\n"
            f"{_meme_visual_prompt_rules(video_format=vf_key)}"
            f"{_SCRIPT_SUBSTANCE_RULES}"
            f"{_SCRIPT_SUBSTANCE_RULES_COMEDY_EXTRA}"
            f"{_tts_block()}"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: deadpan wrongness or fake-sincere doom\n"
            "- Escalation: sitcom argument, sci-fi nonsense, or moral panic — pick one and spiral\n"
            "- Chaos peak: maximum cartoon transgression; one concrete visual gag per beat where possible\n"
            "- Payoff: land the joke\n"
            "- Close/CTA: ironic follow / subscribe bit\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            f"- narration total {_SCRIPT_WORDS}\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items matching the brief’s tone (satire, animation, comedy, viral)\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{fusion}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
            f"{art}"
        )
    if vf_key == "creepypasta":
        return (
            "You are a horror fiction writer for vertical creepypasta shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats. "
            "Original fiction only — no true-crime claims, no real missing persons, no graphic gore.\n"
            "Narration: first-person past-tense campfire voice unless the brief specifies otherwise.\n"
            "Default visuals: atmospheric dread, liminal spaces, implied threat — staging only in `visual_prompt`.\n"
            f"{_meme_visual_prompt_rules(video_format=vf_key)}"
            f"{_SCRIPT_SUBSTANCE_RULES}"
            f"{_tts_block()}"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: wrong detail or quiet wrongness\n"
            "- Rising dread: clues, repetition, uncanny behavior\n"
            "- Twist: one clean fictional reveal\n"
            "- Aftershock: lingering unease\n"
            "- Close/CTA: low-key unsettling sign-off\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            f"- narration total {_SCRIPT_WORDS}\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items (horror fiction, creepypasta, scary shorts — match the brief)\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{fusion}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
            f"{art}"
        )
    if vf_key == "health_advice":
        return (
            "You are a scriptwriter for clinician-led **wellness education** vertical shorts (9:16).\n"
            "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
            "Turn it into a complete script package — faithful to intent, with strict medical-safety rules.\n"
            f"Video format mode: {video_format!r}. Aim for: {vf}\n"
            "Not personal medical advice — no diagnosis of the viewer, no medication changes, no dosing. "
            "Encourage professional care where appropriate.\n"
            f"{_health_visual_prompt_rules(video_format=vf_key)}"
            f"{_SCRIPT_SUBSTANCE_RULES}"
            f"{_tts_block()}"
            f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
            "Enforce this arc (adapt timing across segments):\n"
            "- Hook: caring clinician opens with a clear wellness question\n"
            "- Education: tips and general condition context from the brief\n"
            "- Practical beats: habits viewers might discuss with their clinician\n"
            "- Disclaimer + CTA: not medical advice; follow/subscribe in character\n"
            "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
            "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
            "Constraints:\n"
            f"- narration total {_SCRIPT_WORDS}\n"
            "- title <= 80 chars\n"
            "- hashtags: 15-30 items (wellness, health education, shorts)\n"
            "- avoid markdown except optional ```json fence\n"
            "\n"
            f"{personality_block}"
            f"{char_block}"
            f"{fusion}"
            f"{style_suffix}"
            f"{tag_line}"
            "Creative brief (primary — follow this):\n"
            f"{expanded_brief.strip()}\n"
            f"{art}"
        )
    return (
        "You are a short-form scriptwriter for vertical video (9:16).\n"
        "The PRIMARY source below is a creative brief (from the user's instructions, expanded). "
        "Turn it into a complete script package — you may interpret and tighten, but stay faithful to the user's intent.\n"
        f"Video format mode: {video_format!r}. Aim for: {vf}\n"
        f"Write a {_SCRIPT_RUNTIME} script with {_SCRIPT_SEGMENTS} few-second beats.\n"
        "Style: punchy, factual where needed. Default visuals: bold modern vertical-short look unless the brief says otherwise — visuals only in `visual_prompt`.\n"
        f"{_SCRIPT_SUBSTANCE_RULES}"
        f"{_tts_block()}"
        "Enforce this arc (adapt timing across segments):\n"
        "- Hook: one punchy line (in host voice — see character block)\n"
        "- Context: what it is / setup\n"
        "- Key points: several concrete beats\n"
        "- Why it matters: practical impact / who should care\n"
        "- Close/CTA: short follow/subscribe style line in character\n"
        "Output STRICT JSON with keys: title, description, hashtags, hook, segments, cta.\n"
        "segments must be an array of objects: {narration, visual_prompt, on_screen_text}.\n"
        "Constraints:\n"
        f"- narration total {_SCRIPT_WORDS}\n"
        "- title <= 80 chars\n"
        "- hashtags: 15-30 items aligned with the brief (any subject domain)\n"
        "- avoid markdown except optional ```json fence\n"
        "\n"
        f"{personality_block}"
        f"{char_block}"
        f"{fusion}"
        f"{style_suffix}"
        f"{tag_line}"
        "Creative brief (primary — follow this):\n"
        f"{expanded_brief.strip()}\n"
        f"{art}"
    )


def expand_custom_video_instructions(
    *,
    model_id: str,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    character_context: str | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    try_llm_4bit: bool = True,
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
) -> str:
    """
    First LLM pass for custom Run mode: expand the user's rough notes into a structured creative brief (plain text).
    """
    personality = get_personality_by_id(personality_id)
    fusion = _personality_character_fusion_block(
        personality, character_context, video_format=str(video_format or "news")
    )
    vf = _vf_hint(video_format)
    vf_key = (video_format or "news").strip().lower()
    if vf_key == "cartoon":
        prompt = (
            "You are a creative director for character-driven cartoon shorts (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Pacing: meme-comic / Vine-style — fast setup, punchline, reaction; spoken lines are dialogue or host voice only (no stage directions in spoken beats).\n"
            "The story must be told through characters — specify who speaks, their voices, and how narration maps to beats.\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Cast (names + one-line voice each)\n"
            "3) Core hook (in-character)\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats for ~75–95 seconds) — who says what (spoken lines only)\n"
            "5) Visual motifs (bright 2D cartoon; staging/camera belongs here — not in spoken lines)\n"
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
            "Pacing: meme / Vine energy — rapid beats; spoken lines are character dialogue only (no camera or stage directions in spoken beats).\n"
            "Comedy direction: absurdist satire, cynical banter, shock-cartoon or surreal dread — "
            "invent original characters and settings; do not name or imitate real shows.\n"
            "The story must be told through those characters' voices (not a neutral announcer).\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Cast (who speaks; one-line voice each)\n"
            "3) Core angle / hook (deadpan, wrong-footing, or satirical)\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats for ~75–95 seconds total) — who says what (spoken lines only)\n"
            "5) Visual motifs (default: flat 2D adult-animation satire, exaggerated faces, grotesque-cute or liminal weirdness — "
            "unless notes say otherwise; not corporate cyberpunk by default; for meme topics specify thick outlines, figurative gags, not abstract neon objects)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea (in-character)\n"
            "Keep it tight and actionable.\n"
        )
    elif vf_key == "creepypasta":
        prompt = (
            "You are a creative director for vertical creepypasta / horror-fiction shorts (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Fiction only: no true-crime framing, no real missing persons, no graphic gore instructions.\n"
            "Spoken lines are narrator voice only (no camera or stage directions in spoken beats).\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Narrator persona (name + voice — first-person past tense default)\n"
            "3) Core hook (one uneasy line)\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats for ~75–95 seconds total) — spoken lines only per beat\n"
            "5) Visual motifs (fog, liminal spaces, silhouettes, analog grain — implied dread; not splatter)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea (low-key unsettling)\n"
            "Keep it tight and actionable.\n"
        )
    elif vf_key == "health_advice":
        prompt = (
            "You are a creative director for clinician-led **wellness education** vertical shorts (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Safety: not personal medical advice — no viewer diagnosis, no medication instructions, no graphic injury. "
            "One clinician persona (doctor or nurse), original name.\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Clinician persona (doctor or nurse; name + voice)\n"
            "3) Core hook (caring, clear)\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats) — wellness tips + general condition education (spoken lines only)\n"
            "5) Visual motifs (teaching diagrams, calm clinic or education set — no gore)\n"
            "6) Disclaimer line to speak near the end (not medical advice)\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea (follow + see a professional when needed)\n"
            "Keep it tight and actionable.\n"
        )
    else:
        prompt = (
            "You are a creative director for short-form vertical video (9:16).\n"
            "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Do not assume a subject domain (e.g. AI) unless the user’s notes say so. Anchor everything to their actual topics and intent.\n"
            "Spoken / host voice vs visuals: describe what the host says vs what appears on screen; do not mix camera directions into “lines to say”.\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line)\n"
            "2) Host persona (name + voice — who speaks the whole video)\n"
            "3) Core angle / hook (what the host says first)\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats for ~75–95 seconds total) — spoken lines only per beat\n"
            "5) Visual motifs per beat (graphics, B-roll ideas — not spoken aloud)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes)\n"
            "8) CTA idea\n"
            "Keep it tight and actionable.\n"
        )
    with vram_guard():
        raw = _generate_with_transformers(
            model_id=model_id,
            prompt=prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=1200,
            try_llm_4bit=try_llm_4bit,
            llm_cuda_device_index=llm_cuda_device_index,
            inference_settings=inference_settings,
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
    Skipped for cartoon/unhinged/creepypasta — comedy or horror pacing should not get generic "news explainer" inserts.
    """
    vf = (video_format or "news").strip().lower()
    if vf in ("cartoon", "unhinged", "creepypasta"):
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

    try:
        from src.util.cpu_parallelism import apply_torch_cpu_settings

        apply_torch_cpu_settings(torch)
    except Exception:
        pass

    if not torch.cuda.is_available():
        return False
    try:
        x = torch.tensor([0, 1], device="cuda", dtype=torch.long)
        torch.isin(x, x)
        return True
    except RuntimeError:
        return False


def _llm_max_input_tokens_cap_from_vram() -> int | None:
    """
    When VRAM is tight, lower the tokenizer cap so prefill (attention) does not OOM.

    Returns None if no extra cap should apply (caller uses base defaults only).
    Skipped when ``AQUADUCT_LLM_MAX_INPUT_TOKENS`` is set — user override wins.
    """
    import os

    if (os.environ.get("AQUADUCT_LLM_MAX_INPUT_TOKENS") or "").strip().isdigit():
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        total = int(torch.cuda.get_device_properties(0).total_memory)
    except Exception:
        return None
    # Prefill memory scales badly with sequence length; fp16 7–8B models already
    # consume most of an 8GB card — keep inputs conservative unless user overrides.
    _GIB = 1024**3
    if total < 10 * _GIB:
        return 1536
    if total < 12 * _GIB:
        return 2048
    if total < 16 * _GIB:
        return 3072
    if total < 24 * _GIB:
        return 4096
    return None


def _llm_max_input_tokens_cap(
    tokenizer: Any,
    *,
    model_id: str | None = None,
    inference_settings: AppSettings | None = None,
) -> int:
    """
    Cap prompt length for local ``generate()`` so long article/context strings do not
    blow VRAM during attention prefill (common on ~8GB GPUs).

    Override with env ``AQUADUCT_LLM_MAX_INPUT_TOKENS`` (integer; clamped 256–100000).
    Default: min(4096, tokenizer.model_max_length) when the latter is sane, else 4096,
    then further reduced on low-VRAM CUDA devices (see ``_llm_max_input_tokens_cap_from_vram``).
    When ``inference_settings`` is set, also min with the script inference profile
    (same effective VRAM as GPU policy fit badges for the script role).
    """
    import os

    raw = (os.environ.get("AQUADUCT_LLM_MAX_INPUT_TOKENS") or "").strip()
    if raw.isdigit():
        return max(256, min(int(raw), 100_000))
    default_cap = 4096
    mm = getattr(tokenizer, "model_max_length", None)
    if isinstance(mm, int) and 0 < mm < 100_000:
        base = min(default_cap, mm)
    else:
        base = default_cap
    vram_cap = _llm_max_input_tokens_cap_from_vram()
    if vram_cap is not None:
        base = min(base, vram_cap)
    if (model_id or "").strip() and inference_settings is not None:
        try:
            from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

            v = resolve_effective_vram_gb(kind="script", settings=inference_settings)
            sp = pick_script_profile((model_id or "").strip(), v)
            base = min(base, int(sp.max_input_tokens))
        except Exception:
            pass
    return base


def load_causal_lm_from_pretrained(
    load_path: str,
    *,
    try_4bit: bool = True,
    on_status: Callable[[str], None] | None = None,
    cuda_device_index: int | None = None,
    quant_mode: str | None = None,
) -> Any:
    """
    Load ``AutoModelForCausalLM`` from disk or Hub id with an explicit quantization mode.

    ``quant_mode`` (preferred): ``auto`` | ``bf16`` | ``fp16`` | ``int8`` | ``nf4_4bit`` | ``cpu_offload``.
    When unset, falls back to legacy ``try_4bit`` boolean (``nf4_4bit`` if True else ``fp16``).

    Each mode falls back to fp16 / CPU on failure with a status message.
    """
    from src.models.hf_transformers_imports import causal_lm_stack
    from src.models.torch_dtypes import torch_float16

    AutoModelForCausalLM, _, BitsAndBytesConfig = causal_lm_stack()
    _fp16 = torch_float16()
    cuda_ok = torch_cuda_kernels_work()

    def _status(msg: str) -> None:
        if on_status:
            on_status(msg)

    # Resolve effective mode from explicit quant_mode (preferred) or legacy try_4bit.
    qm = (quant_mode or "").strip().lower()
    if not qm:
        qm = "nf4_4bit" if bool(try_4bit) else "fp16"
    if qm not in ("auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"):
        qm = "auto"

    def _device_map_for_load() -> Any:
        if cuda_device_index is not None and cuda_ok:
            try:
                torch.cuda.set_device(int(cuda_device_index))
            except Exception:
                pass
            return {"": int(cuda_device_index)}
        return "auto"

    def _bf16_dtype() -> Any:
        try:
            return torch.bfloat16
        except Exception:
            return _fp16

    def _from_pretrained(*, quantization_config: Any | None, device_map: Any, dtype: Any) -> Any:
        if quantization_config is not None:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    quantization_config=quantization_config,
                    device_map=device_map,
                    dtype=dtype,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )
            except TypeError:
                try:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=dtype,
                        low_cpu_mem_usage=True,
                        trust_remote_code=True,
                    )
                except TypeError:
                    return AutoModelForCausalLM.from_pretrained(
                        load_path,
                        quantization_config=quantization_config,
                        device_map=device_map,
                        torch_dtype=dtype,
                        trust_remote_code=True,
                    )
        try:
            return AutoModelForCausalLM.from_pretrained(
                load_path,
                device_map=device_map,
                dtype=dtype,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
            )
        except TypeError:
            try:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=dtype,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )
            except TypeError:
                return AutoModelForCausalLM.from_pretrained(
                    load_path,
                    device_map=device_map,
                    torch_dtype=dtype,
                    trust_remote_code=True,
                )

    if not cuda_ok:
        _status("CUDA unusable for this GPU/driver build; loading LLM on CPU (slower)…")
        return _from_pretrained(quantization_config=None, device_map="cpu", dtype=_fp16)

    dm = _device_map_for_load()

    # Map "auto" using effective VRAM heuristic (best-effort; no settings here means default policy).
    if qm == "auto":
        try:
            from src.models.hardware import list_cuda_gpus
            from src.models.quantization import pick_auto_mode

            gpus = list_cuda_gpus()
            v = None
            if gpus and cuda_device_index is not None:
                for g in gpus:
                    if g.index == int(cuda_device_index):
                        v = g.total_vram_gb
                        break
            elif gpus:
                v = gpus[0].total_vram_gb
            qm = str(pick_auto_mode(role="script", repo_id="", vram_gb=v, cuda_ok=True))
        except Exception:
            qm = "nf4_4bit"

    def _try_bnb_4bit() -> Any:
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=_fp16,
        )
        _status("Loading model (NF4 4-bit)…")
        return _from_pretrained(quantization_config=bnb, device_map=dm, dtype=_fp16)

    def _try_bnb_8bit() -> Any:
        bnb = BitsAndBytesConfig(load_in_8bit=True)
        _status("Loading model (INT8 / 8-bit)…")
        return _from_pretrained(quantization_config=bnb, device_map=dm, dtype=_fp16)

    def _try_bf16() -> Any:
        _status("Loading model (BF16)…")
        return _from_pretrained(quantization_config=None, device_map=dm, dtype=_bf16_dtype())

    def _try_fp16() -> Any:
        _status("Loading model (FP16)…")
        return _from_pretrained(quantization_config=None, device_map=dm, dtype=_fp16)

    def _try_cpu() -> Any:
        _status("Loading model on CPU offload (FP16)…")
        return _from_pretrained(quantization_config=None, device_map="cpu", dtype=_fp16)

    chain: list[tuple[str, Any]] = []
    if qm == "nf4_4bit":
        chain = [("NF4 4-bit", _try_bnb_4bit), ("INT8", _try_bnb_8bit), ("FP16", _try_fp16), ("CPU FP16", _try_cpu)]
    elif qm == "int8":
        chain = [("INT8", _try_bnb_8bit), ("NF4 4-bit", _try_bnb_4bit), ("FP16", _try_fp16), ("CPU FP16", _try_cpu)]
    elif qm == "bf16":
        chain = [("BF16", _try_bf16), ("FP16", _try_fp16), ("INT8", _try_bnb_8bit), ("CPU FP16", _try_cpu)]
    elif qm == "cpu_offload":
        chain = [("CPU FP16", _try_cpu), ("FP16", _try_fp16)]
    else:  # fp16 / fallback
        chain = [("FP16", _try_fp16), ("INT8", _try_bnb_8bit), ("NF4 4-bit", _try_bnb_4bit), ("CPU FP16", _try_cpu)]

    last_err: Exception | None = None
    for label, fn in chain:
        try:
            return fn()
        except Exception as e:
            last_err = e
            _status(f"{label} load failed ({type(e).__name__}); falling back…")
    if last_err is not None:
        raise last_err
    return _try_fp16()


def _generate_with_transformers(
    model_id: str,
    prompt: str,
    *,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 650,
    try_llm_4bit: bool = True,
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    quant_mode: str | None = None,
) -> str:
    import torch

    try:
        from src.util.cpu_parallelism import apply_torch_cpu_settings

        apply_torch_cpu_settings(torch)
    except Exception:
        pass

    from src.models.hf_access import ensure_hf_token_in_env
    from src.models.hf_transformers_imports import causal_lm_stack, text_iterator_streamer_cls

    # Gated Hub models need HF_TOKEN before tokenizer/model load; refresh from disk if env empty.
    ensure_hf_token_in_env(hf_token="")

    _, AutoTokenizer, _ = causal_lm_stack()

    def _stderr(msg: str) -> None:
        if not on_llm_task:
            import sys

            print(f"[Aquaduct] {msg}", file=sys.stderr, flush=True)

    def _load_status(detail: str) -> None:
        _emit_llm(on_llm_task, "llm_load", 55, detail)

    # Load from project `models/<repo>/` when present; plain repo id uses HF cache (extra downloads).
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())

    _emit_llm(on_llm_task, "llm_load", 0, "Loading tokenizer…")
    tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=True, trust_remote_code=True)
    _emit_llm(on_llm_task, "llm_load", 25, "Tokenizer ready")

    _emit_llm(on_llm_task, "llm_load", 30, "Loading model weights…")
    # Prefer explicit quant_mode; else inference_settings.script_quant_mode; else legacy try_llm_4bit.
    _qmode = quant_mode
    if not _qmode and inference_settings is not None:
        _qmode = str(getattr(inference_settings, "script_quant_mode", "") or "") or None
    model = load_causal_lm_from_pretrained(
        load_path,
        try_4bit=bool(try_llm_4bit),
        on_status=_load_status,
        cuda_device_index=llm_cuda_device_index,
        quant_mode=_qmode,
    )
    _emit_llm(on_llm_task, "llm_load", 100, "Model loaded")

    # Simple chat-ish formatting without requiring tokenizer chat template support.
    full = f"### Instruction:\n{prompt}\n\n### Response:\n"
    _cap = _llm_max_input_tokens_cap(tokenizer, model_id=model_id, inference_settings=inference_settings)
    max_new_use = int(max_new_tokens)
    if inference_settings is not None:
        try:
            from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

            v = resolve_effective_vram_gb(kind="script", settings=inference_settings)
            sp = pick_script_profile((model_id or "").strip(), v)
            max_new_use = min(max_new_use, int(sp.max_new_tokens))
        except Exception:
            pass
    inputs = tokenizer(
        full,
        return_tensors="pt",
        truncation=True,
        max_length=_cap,
    ).to(model.device)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

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
            "max_new_tokens": max_new_use,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9,
            "repetition_penalty": 1.08,
            "eos_token_id": tokenizer.eos_token_id,
        }

        def _run_gen() -> None:
            with torch.inference_mode():
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                model.generate(**generation_kwargs)

        th = Thread(target=_run_gen, daemon=True)
        th.start()
        chunks: list[str] = []
        n_tok = 0
        for text in streamer:
            chunks.append(text)
            n_tok += 1
            pct = min(99, int(100 * n_tok / max(1, max_new_use)))
            _emit_llm(
                on_llm_task,
                "llm_generate",
                pct,
                f"Generating tokens ({n_tok}/{max_new_use})",
            )
        th.join(timeout=7200)
        raw_new = "".join(chunks)
        _emit_llm(on_llm_task, "llm_generate", 100, "Generation finished")
    except Exception as e:
        dprint("brain", "streamed generation failed, falling back", str(e))
        _emit_llm(on_llm_task, "llm_generate", 10, "Fallback: one-shot generate…")
        with torch.inference_mode():
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_use,
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
    article_excerpt: str | None = None,
    supplement_context: str = "",
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
) -> VideoPackage:
    """
    Generates a structured video package from scraped headlines/links, or from a pre-expanded custom creative brief.
    Tries local 4-bit transformers; falls back to a deterministic template if the model fails to load.
    """
    personality = get_personality_by_id(personality_id)
    ex = clip_article_excerpt(article_excerpt)
    if creative_brief is not None and str(creative_brief).strip():
        prompt = _prompt_for_creative_brief(
            expanded_brief=str(creative_brief),
            topic_tags=topic_tags,
            video_format=str(video_format or "news"),
            personality=personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=ex,
        )
    else:
        prompt = _prompt_for_items(
            items,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            video_format=str(video_format or "news"),
            article_excerpt=ex,
        )
    sup = (supplement_context or "").strip()
    if sup:
        prompt = prompt + _supplement_context_block(sup)
    mode = "custom_brief" if (creative_brief is not None and str(creative_brief).strip()) else "headlines"
    dprint("brain", "generate_script start", f"model_id={model_id!r}", f"mode={mode!r}", f"items={len(items)}", f"personality={personality_id!r}")

    with vram_guard():
        try:
            raw = _generate_with_transformers(
                model_id=model_id,
                prompt=prompt,
                on_llm_task=on_llm_task,
                max_new_tokens=2048,
                try_llm_4bit=try_llm_4bit,
                llm_cuda_device_index=llm_cuda_device_index,
                inference_settings=inference_settings,
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
                            narration="I’m telling you right now — this headline walked in like it owned the place.",
                            visual_prompt="flat 2D adult cartoon, deadpan characters, liminal suburban background, 9:16",
                            on_screen_text="COLD OPEN",
                        ),
                        ScriptSegment(
                            narration="Nobody agreed on anything, so naturally we escalated until someone yelled about morality.",
                            visual_prompt="exaggerated TV-comedy staging, gross-out reaction shots, comic panels, speed lines, 9:16",
                            on_screen_text="ESCALATE",
                        ),
                        ScriptSegment(
                            narration="We stick the landing before the bit gets old — subscribe if you’re still sane.",
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
            if vf_fallback == "creepypasta":
                seed = (items[0].get("title") if items else "") or "The hallway"
                title = seed[:80]
                hook = "I found a thread online that should have stayed buried — let me tell you what it did to my head."
                hashtags = [
                    "#Creepypasta",
                    "#HorrorShorts",
                    "#ScaryStory",
                    "#UrbanLegend",
                    "#Spooky",
                    "#HorrorTok",
                    "#GhostStory",
                    "#Liminal",
                    "#Unsettling",
                    "#Shorts",
                    "#Fiction",
                    "#Narrator",
                    "#Dark",
                    "#Paranormal",
                    "#Haunted",
                    "#Creepy",
                    "#Storytime",
                ]
                pkg = VideoPackage(
                    title=title,
                    description=f"Original horror short riff inspired by online fiction titles: {seed}",
                    hashtags=hashtags[:30],
                    hook=hook,
                    segments=[
                        ScriptSegment(
                            narration="It started as a joke — a link, a title too specific to be random.",
                            visual_prompt="dim hallway, single flickering bulb, long shadows, grainy photo, 9:16",
                            on_screen_text="SETUP",
                        ),
                        ScriptSegment(
                            narration="The more I read, the more the house felt like it leaned closer — wrong angles, wrong silence.",
                            visual_prompt="empty room at night, moonlight through blinds, silhouette in doorway, 9:16",
                            on_screen_text="DREAD",
                        ),
                        ScriptSegment(
                            narration="If you’re still listening — don’t go looking for the rest. Some doors are better left unclicked.",
                            visual_prompt="close-up of a cracked phone screen glow on face, fog, 9:16",
                            on_screen_text="OUTRO",
                        ),
                    ],
                    cta="Follow for more creepypasta shorts — fiction only.",
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
                dprint("brain", "generate_script ok (fallback creepypasta)", f"title={pkg.title[:100]!r}")
                return pkg
            # Fallback: minimal structured script without the LLM (keeps pipeline running).
            story_title = (items[0].get("title") if items else "") or "this story"
            title = story_title[:80]
            st_short = story_title[:90] if len(story_title) > 90 else story_title

            # Tone shaping for fallback (host voice — topic-agnostic)
            if personality.id == "hype":
                hook = f"Stop scrolling — you need to hear what’s going on with {st_short}."
                cta = "Follow for more fast rundowns like this."
            elif personality.id == "analytical":
                hook = f"Quick breakdown: what matters in {st_short}."
                cta = "Follow for clear takes and real detail."
            elif personality.id == "comedic":
                hook = f"Okay, {st_short} — I’m not emotionally ready, but here we go."
                cta = "Follow for more unserious seriousness."
            elif personality.id == "skeptical":
                hook = f"Before you buy the hype — here’s the honest read on {st_short}."
                cta = "Follow for skeptical breakdowns."
            elif personality.id == "cozy":
                hook = f"Hey — quick and simple: what you should know about {st_short}."
                cta = "Follow for friendly explainers."
            elif personality.id == "urgent":
                hook = f"This is moving fast — here’s {st_short} in plain English."
                cta = "Follow for updates you can use."
            elif personality.id == "contrarian":
                hook = f"Hot take: everyone’s missing the point on {st_short}."
                cta = "Follow for sharper angles."
            else:
                hook = f"Here’s the rundown on {st_short}."
                cta = "Follow for more shorts like this."

            extra_tags: list[str] = []
            for t in topic_tags or []:
                t2 = re.sub(r"[^A-Za-z0-9]+", "", (t or "").strip())
                if t2:
                    extra_tags.append("#" + t2[:28])
            base_tags = [
                "#Shorts",
                "#Video",
                "#News",
                "#Watch",
                "#Breaking",
                "#Update",
                "#Story",
                "#Explainer",
                "#Trending",
                "#FYP",
                "#Vertical",
                "#Quick",
                "#Rundown",
                "#Today",
                "#Topics",
            ]
            merged_ht = _normalize_hashtags(base_tags + extra_tags)[:30]

            pkg = VideoPackage(
                title=title,
                description=f"Fast take: {story_title}. What happened, why people care, and what to watch for.",
                hashtags=merged_ht,
                hook=hook,
                segments=[
                    ScriptSegment(
                        narration=f"Alright — {story_title}. Here’s what you need to know first.",
                        visual_prompt="bold news-style vertical graphic, dynamic typography, clean layout, 9:16",
                        on_screen_text="LEAD",
                    ),
                    ScriptSegment(
                        narration="Here’s the core of what happened — the facts, plain and simple.",
                        visual_prompt="split-panel infographic, icons, readable labels, vertical 9:16",
                        on_screen_text="WHAT HAPPENED",
                    ),
                    ScriptSegment(
                        narration="Who this hits hardest — and why people are reacting the way they are.",
                        visual_prompt="dynamic portraits silhouettes or crowd graphic, bold color, 9:16",
                        on_screen_text="WHO CARES",
                    ),
                    ScriptSegment(
                        narration="My read: watch what happens next — that’s the part that actually matters.",
                        visual_prompt="timeline arrow, bold headline strip, vertical 9:16",
                        on_screen_text="TAKEAWAY",
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


def generate_cast_from_storyline_llm(
    *,
    model_id: str,
    video_format: str,
    storyline_title: str,
    storyline_text: str,
    topic_tags: list[str] | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int = 1200,
    try_llm_4bit: bool = True,
) -> list[dict[str, Any]]:
    """
    Generate an ephemeral per-run cast (not saved to global characters.json).

    - News/explainer: 1 narrator/host character.
    - Cartoon/unhinged: at least 2 distinct characters whose roles fit the plot.
    """
    vf = (video_format or "news").strip().lower()
    min_chars = 1 if vf in ("news", "explainer") else 2
    tags = [t.strip() for t in (topic_tags or []) if isinstance(t, str) and t.strip()][:12]
    tags_line = json.dumps(tags, ensure_ascii=False)
    st = (storyline_text or "").strip()
    if len(st) > 8000:
        st = st[:7999] + "…"
    title = (storyline_title or "").strip()[:160]
    prompt = (
        "You create ORIGINAL characters for a short-form vertical video (9:16).\n"
        "Goal: generate a cast that matches the storyline and the selected video format mode.\n"
        f"Video format: {vf!r}\n"
        f"Minimum characters: {min_chars}\n"
        f"Topic tags (optional bias): {tags_line}\n\n"
        "Story title:\n"
        f"{title}\n\n"
        "Storyline (spoken narration + beat summaries; use to align character roles and relationships):\n"
        f"{st}\n\n"
        "Output STRICT JSON ONLY with this schema:\n"
        "{\n"
        '  "characters": [\n'
        "    {\n"
        '      "name": string,\n'
        '      "role": string,\n'
        '      "identity": string,\n'
        '      "visual_style": string,\n'
        '      "negatives": string\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- Return at least {min_chars} characters.\n"
        "- Do not imitate real celebrities or copyrighted characters.\n"
        "- For news/explainer: keep it a single narrator/host.\n"
        "- For cartoon/unhinged: make the story playable as dialogue between the cast.\n"
        "- Output ONLY valid JSON (no markdown fences, no extra text).\n"
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
    if not isinstance(blob, dict):
        raise ValueError("Cast generator did not return JSON object.")
    chars = blob.get("characters")
    if not isinstance(chars, list):
        raise ValueError("Cast generator JSON missing characters[].")
    out: list[dict[str, Any]] = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        role = str(c.get("role") or "").strip()
        identity = str(c.get("identity") or "").strip()
        visual_style = str(c.get("visual_style") or "").strip()
        negatives = str(c.get("negatives") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name[:120],
                "role": role[:240],
                "identity": identity[:8000],
                "visual_style": visual_style[:8000],
                "negatives": negatives[:8000],
            }
        )
        if len(out) >= 6:
            break
    if len(out) < min_chars:
        raise ValueError("Cast generator returned too few characters.")
    return out


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

