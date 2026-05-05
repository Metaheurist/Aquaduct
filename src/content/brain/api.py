"""Public brain entrypoints: script, cast, character preset, topic grounding, field expand."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

from src.render.branding_video import palette_prompt_suffix
from src.content.topic_constraints import parse_topic_grounding_llm_json
from src.util.llm_json_extract import parse_first_json_dict_from_llm_text
from src.util.utils_vram import vram_guard

from ..character_presets import (
    CharacterAutoPreset,
    GeneratedCharacterFields,
    coerce_generated_character_fields,
)
from ..nsfw_guardrails import nsfw_llm_guardrails_block
from ..personalities import PersonalityPreset, get_personality_by_id

from debug import dprint

from .package import (
    VideoPackage,
    ScriptSegment,
    clip_article_excerpt,
    enforce_arc,
    _normalize_hashtags,
    video_package_from_llm_output,
    _fallback_package_custom,
    _to_package,
)
from .prompts import (
    _SCRIPT_SEGMENTS,
    _personality_character_fusion_block,
    _prompt_for_creative_brief,
    _prompt_for_items,
    _series_continuity_block,
    _supplement_context_block,
    _vf_hint,
)
from .runtime import _generate_with_transformers, _infer_text_with_optional_holder

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
    llm_holder: MutableMapping[str, Any] | None = None,
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
    elif vf_key == "nsfw":
        g = nsfw_llm_guardrails_block()
        prompt = (
            "You are a creative director for **adults-only** performer-led vertical shorts (9:16).\n"
            + (f"{g}\n" if g else "")
            + "The user wrote rough notes. Expand them into a structured creative brief. "
            "Do NOT output JSON. Use clear plain text with labeled sections.\n"
            f"Video format mode: {video_format!r}. Target style: {vf}\n"
            "Fiction / entertainment framing only — consenting adults (21+), no real public figures, no illegal themes.\n"
            f"{fusion}"
            f"Tone anchor — {personality.label}: {personality.description}\n"
            "Style rules to respect:\n"
            + "\n".join(f"- {r}" for r in personality.style_rules)
            + "\n\nUser's raw notes:\n"
            f"{raw_instructions.strip()}\n\n"
            "Output sections (use headings):\n"
            "1) Working title (one line; professional wording)\n"
            "2) Performer/host persona (stage name + voice)\n"
            "3) Hook + spoken 18+ disclaimer line\n"
            f"4) Beat-by-beat outline ({_SCRIPT_SEGMENTS} beats) — spoken lines only\n"
            "5) Visual motifs (tasteful studio / editorial moods — staging here, not in spoken lines)\n"
            "6) Short on-screen text keywords per beat\n"
            "7) Hashtag theme words (no # prefixes; tame industry labels)\n"
            "8) CTA idea (in-character)\n"
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
        raw = _infer_text_with_optional_holder(
            model_id,
            prompt,
            llm_holder=llm_holder,
            on_llm_task=on_llm_task,
            max_new_tokens=1200,
            try_llm_4bit=try_llm_4bit,
            llm_cuda_device_index=llm_cuda_device_index,
            inference_settings=inference_settings,
        )
    return raw.strip()
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
    previous_episode_summary: str = "",
    series_bible: str = "",
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    llm_holder: MutableMapping[str, Any] | None = None,
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
    _cont = _series_continuity_block(
        previous_episode_summary=previous_episode_summary,
        series_bible=series_bible,
    )
    if _cont:
        prompt = prompt + _cont
    mode = "custom_brief" if (creative_brief is not None and str(creative_brief).strip()) else "headlines"
    dprint("brain", "generate_script start", f"model_id={model_id!r}", f"mode={mode!r}", f"items={len(items)}", f"personality={personality_id!r}")

    with vram_guard():
        try:
            raw = _infer_text_with_optional_holder(
                model_id,
                prompt,
                llm_holder=llm_holder,
                on_llm_task=on_llm_task,
                max_new_tokens=2048,
                try_llm_4bit=try_llm_4bit,
                llm_cuda_device_index=llm_cuda_device_index,
                inference_settings=inference_settings,
            )
            data = _extract_json(raw)
            pkg = _to_package(data, video_format=str(video_format or ""))
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
    inference_settings: AppSettings | None = None,
    video_format: str | None = None,
) -> GeneratedCharacterFields:
    """
    Use the script LLM to invent a full character profile (text fields) from a built-in archetype.
    Does not assign pyttsx3 / ElevenLabs IDs — user picks voices in the UI.
    """
    from ..characters_store import CHARACTER_FIELD_MAX_LEN, CHARACTER_NAME_MAX_LEN
    from ..characters.presets import (
        CHARACTER_AGE_RANGE_OPTIONS,
        CHARACTER_ETHNICITY_OPTIONS,
        CHARACTER_GENDER_OPTIONS,
        CHARACTER_VOICE_INSTRUCTION_OPTIONS,
    )

    notes = (extra_notes or "").strip()
    notes_block = f"Extra notes from the user (optional):\n{notes}\n" if notes else ""

    arch = (preset.llm_directive or "").strip() or "Original short-form video host."
    vf = (video_format or "").strip().lower()
    pid = (preset.id or "").strip().lower()
    guard = ""
    if vf == "nsfw" or pid.startswith("nsfw_"):
        gblk = nsfw_llm_guardrails_block()
        guard = (gblk + "\n") if gblk else ""
    allowed_gender = [v for _l, v in CHARACTER_GENDER_OPTIONS]
    allowed_eth = [v for _l, v in CHARACTER_ETHNICITY_OPTIONS]
    allowed_age = [v for _l, v in CHARACTER_AGE_RANGE_OPTIONS]
    allowed_vi = [v for _l, v in CHARACTER_VOICE_INSTRUCTION_OPTIONS]
    prompt = (
        "You help users of a desktop short-form video app (9:16 vertical).\n"
        f"{guard}"
        "Invent ONE original host character — not a real celebrity, brand mascot, or copyrighted figure.\n\n"
        f"Archetype label: {preset.label}\n"
        f"Creative direction for this archetype:\n{arch}\n\n"
        f"{notes_block}"
        "The UI uses dropdowns for a few fields. You MUST choose from the allowed values exactly.\n"
        f"Allowed gender values: {allowed_gender}\n"
        f"Allowed ethnicity values: {allowed_eth}\n"
        f"Allowed age_range values: {allowed_age}\n"
        f"Allowed voice_instruction values: {allowed_vi}\n\n"
        "Output a single JSON object with EXACTLY these keys:\n"
        '- "name": short memorable display name (string)\n'
        '- "identity": persona for script + on-screen context — tone, audience, how they talk (string, several sentences)\n'
        '- "visual_style": string to prepend to image prompts — look, lighting, wardrobe, set (several short sentences)\n'
        '- "negatives": comma-separated diffusion negative prompts to reduce artifacts (string)\n'
        '- "use_default_voice": boolean — true if a generic project TTS is fine; false if the character needs a distinct voice pick\n'
        '- "gender": one of the allowed gender values above (string)\n'
        '- "ethnicity": one of the allowed ethnicity values above (string)\n'
        '- "age_range": one of the allowed age_range values above (string)\n'
        '- "voice_instruction": one of the allowed voice_instruction values above (string)\n'
        "\n"
        "Rules:\n"
        "- Output ONLY valid JSON. No markdown fences, no commentary before or after.\n"
        "- Do not include keys other than the nine above.\n"
        "- Keep everything original; no real-person imitation.\n"
    )
    with vram_guard():
        raw = _generate_with_transformers(
            model_id,
            prompt,
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            try_llm_4bit=try_llm_4bit,
            inference_settings=inference_settings,
        )
    blob = parse_first_json_dict_from_llm_text(raw or "")
    coerced = coerce_generated_character_fields(blob)
    if coerced is None:
        raise ValueError("Model did not return usable JSON with name, identity, and visual fields.")
    return GeneratedCharacterFields(
        name=coerced.name[:CHARACTER_NAME_MAX_LEN],
        identity=coerced.identity[:CHARACTER_FIELD_MAX_LEN],
        visual_style=coerced.visual_style[:CHARACTER_FIELD_MAX_LEN],
        negatives=coerced.negatives[:CHARACTER_FIELD_MAX_LEN],
        use_default_voice=coerced.use_default_voice,
        gender=coerced.gender[:256],
        ethnicity=coerced.ethnicity[:256],
        age_range=coerced.age_range[:256],
        voice_instruction=coerced.voice_instruction[:256],
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
    llm_cuda_device_index: int | None = None,
    inference_settings: AppSettings | None = None,
    llm_holder: MutableMapping[str, Any] | None = None,
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
        '      "negatives": string,\n'
        '      "voice_instruction": string,\n'
        '      "gender": string,\n'
        '      "ethnicity": string,\n'
        '      "age_range": string\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- Return at least {min_chars} characters.\n"
        "- Do not imitate real celebrities or copyrighted characters.\n"
        "- For news/explainer: keep it a single narrator/host.\n"
        "- For cartoon/unhinged: make the story playable as dialogue between the cast.\n"
        "- voice_instruction: a short free-form TTS direction describing timbre, age range, energy, "
        "  and pacing for this character (e.g. 'mid-30s male, gravelly, slow campfire delivery'). "
        "  Keep under 200 chars. Used by MOSS-VoiceGenerator and ElevenLabs. Skip celebrity comparisons.\n"
        "- gender, ethnicity, age_range: short original labels for visual + narration consistency "
        "  (no real-person imitation; avoid slurs); age_range may be like \"late 20s\" or empty.\n"
        "- Output ONLY valid JSON (no markdown fences, no extra text).\n"
    )

    with vram_guard():
        raw = _infer_text_with_optional_holder(
            model_id,
            prompt,
            llm_holder=llm_holder,
            on_llm_task=on_llm_task,
            max_new_tokens=max_new_tokens,
            try_llm_4bit=try_llm_4bit,
            llm_cuda_device_index=llm_cuda_device_index,
            inference_settings=inference_settings,
        )
    blob = parse_first_json_dict_from_llm_text(raw or "")
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
        voice_instruction = str(c.get("voice_instruction") or "").strip()
        gender = str(c.get("gender") or "").strip()
        ethnicity = str(c.get("ethnicity") or "").strip()
        age_range = str(c.get("age_range") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name[:120],
                "role": role[:240],
                "identity": identity[:8000],
                "visual_style": visual_style[:8000],
                "negatives": negatives[:8000],
                "voice_instruction": voice_instruction[:8000],
                "gender": gender[:256],
                "ethnicity": ethnicity[:256],
                "age_range": age_range[:256],
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
    inference_settings: AppSettings | None = None,
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
            inference_settings=inference_settings,
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


_TOPIC_GROUNDING_SYSTEM_MESSAGE = (
    "You configure short vertical-video topic tags. "
    'Your entire reply must be exactly one JSON object: first character "{", last character "}". '
    "No markdown code fences, no bullet lists, no section headers like Example, no commentary before or after the JSON."
)

# Small batches keep chat-template inputs under truncation caps and completion JSON bounded per forward.
TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK = 6


def topic_grounding_pair_chunks(
    pairs: Sequence[tuple[str, str]],
    *,
    chunk_size: int | None = None,
) -> list[list[tuple[str, str]]]:
    """Split normalized ``(norm, display)`` pairs into fixed-size chunks (always at least one chunk)."""
    sz = max(1, int(chunk_size or TOPIC_GROUNDING_MAX_TAGS_PER_CHUNK))
    lst = list(pairs)
    if not lst:
        return []
    return [lst[i : i + sz] for i in range(0, len(lst), sz)]


def _prompt_topic_tag_grounding_batch(
    tag_pairs: Sequence[tuple[str, str]],
    video_format: str,
    *,
    sibling_displays: Sequence[str],
    seed_notes_by_norm: Mapping[str, str] | None,
) -> str:
    """User-turn body for topic grounding (JSON contract first so input truncation keeps instructions)."""
    vf = str(video_format or "news").strip() or "news"
    siblings = ", ".join(x.strip() for x in sibling_displays if str(x or "").strip())[:900]
    rows: list[str] = []
    for norm, disp in tag_pairs:
        cur = ((seed_notes_by_norm or {}).get(norm) or "").strip()
        disp_safe = str(disp or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
        row = f"{norm}\t{disp_safe}"
        if cur:
            cur_s = cur.replace("\t", " ").replace("\r", " ").replace("\n", " ")
            row += f"\t{cur_s[:220]}{'…' if len(cur_s) > 220 else ''}"
        rows.append(row)
    joined = "\n".join(rows)
    sibling_block = ""
    if siblings.strip():
        sibling_block = (
            f"\nOther tags in this mode (for consistency only; still emit one note per requested key): {siblings}\n"
        )

    return (
        "JSON schema (fill every key from column 1 below; values are grounding lines for the script engine):\n"
        '{"notes": {<tag_norm_ascii_lowercase>: "<one line, plain text, max 240 chars>", ...}}\n\n'
        'Example shape only: {"notes": {"climate_policy": "Science explainers; stay factual; no panic hooks."}}\n\n'
        f'Mode bucket: "{vf}" — match idioms audiences expect for this mode.{sibling_block}\n'
        "Each grounding line: tone, angles, hard bans, genre facts the script must respect.\n\n"
        "Tag rows (tab-separated). Column 1 is the JSON object key you must use exactly; "
        "column 2 is the display label for context; column 3, if present, is the existing note to refine or replace.\n"
        f"{joined}\n"
    )


def generate_topic_tag_grounding_notes_llm(
    *,
    model_id: str,
    tag_pairs: Sequence[tuple[str, str]],
    video_format: str,
    sibling_displays: Sequence[str] | None = None,
    seed_notes_by_norm: Mapping[str, str] | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
    max_new_tokens: int | None = None,
    try_llm_4bit: bool = True,
    inference_settings: AppSettings | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    pairs = [(str(n).strip().lower(), str(d).strip()) for n, d in tag_pairs if str(n or "").strip()]
    if not pairs:
        return {}, ()

    siblings = sibling_displays if sibling_displays is not None else [d for _, d in pairs]
    chunks = topic_grounding_pair_chunks(pairs)
    n_chunks = len(chunks)
    allowed_all = frozenset(n for n, _ in pairs)
    merged_notes: dict[str, str] = {}

    def _scale_llm_progress(chunk_idx: int, task: str, inner_pct: int, msg: str) -> None:
        if on_llm_task is None:
            return
        inner_f = max(0.0, min(1.0, inner_pct / 100.0))
        overall = int(100 * (chunk_idx + inner_f) / n_chunks)
        if chunk_idx >= n_chunks - 1 and inner_pct >= 100:
            overall = 100
        overall = max(0, min(100, overall))
        on_llm_task(task, overall, f"Tags batch {chunk_idx + 1}/{n_chunks}: {msg}")

    with vram_guard():
        for idx, chunk_pairs in enumerate(chunks):
            prompt = _prompt_topic_tag_grounding_batch(
                chunk_pairs,
                video_format,
                sibling_displays=siblings,
                seed_notes_by_norm=seed_notes_by_norm,
            )
            nt = max_new_tokens
            if nt is None:
                nt = min(4096, 320 + len(chunk_pairs) * 220)

            def _on_chunk(task: str, pct: int, msg: str) -> None:
                _scale_llm_progress(idx, task, pct, msg)

            raw = _infer_text_with_optional_holder(
                model_id,
                "",
                llm_holder=None,
                messages=[
                    {"role": "system", "content": _TOPIC_GROUNDING_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                on_llm_task=_on_chunk,
                max_new_tokens=nt,
                try_llm_4bit=try_llm_4bit,
                inference_settings=inference_settings,
                relax_short_json_batch=True,
            )
            allowed_chunk = frozenset(n for n, _ in chunk_pairs)
            notes, _missing = parse_topic_grounding_llm_json(
                raw or "",
                allowed_normalized_tags=allowed_chunk,
            )
            merged_notes.update(notes)

    missing_final = tuple(sorted(t for t in allowed_all if t not in merged_notes))
    return merged_notes, missing_final
