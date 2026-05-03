from __future__ import annotations

from typing import Callable, Mapping, Sequence

from src.content.character_presets import (
    CharacterAutoPreset,
    GeneratedCharacterFields,
    coerce_generated_character_fields,
    extract_first_json_object,
)
from src.content.brain import (
    VideoPackage,
    _prompt_for_creative_brief,
    _prompt_for_items,
    _prompt_topic_tag_grounding_batch,
    _series_continuity_block,
    _supplement_context_block,
    clip_article_excerpt,
    get_personality_by_id,
    topic_grounding_pair_chunks,
    video_package_from_llm_output,
)
from src.content.topic_constraints import parse_topic_grounding_llm_json
from src.content.characters_store import CHARACTER_FIELD_MAX_LEN, CHARACTER_NAME_MAX_LEN
from src.core.config import AppSettings, BrandingSettings
from src.platform.openai_client import build_openai_client_from_settings

SCRIPT_JSON_SYSTEM = (
    "You are an expert short-form vertical video writer. "
    "Return ONLY valid JSON for a VideoPackage: keys title, description, hashtags (array of strings), "
    "hook, segments (array of {narration, visual_prompt, on_screen_text}), cta. "
    "No markdown, no code fences, no commentary."
)


def _llm_model(settings: AppSettings) -> str:
    am = getattr(settings, "api_models", None)
    llm = getattr(am, "llm", None) if am is not None else None
    m = str(getattr(llm, "model", "") or "").strip()
    return m or "gpt-4o-mini"


def generate_script_openai(
    *,
    settings: AppSettings,
    items: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality_id: str,
    branding: BrandingSettings | None,
    character_context: str | None,
    creative_brief: str | None,
    video_format: str,
    article_excerpt: str | None,
    supplement_context: str = "",
    previous_episode_summary: str = "",
    series_bible: str = "",
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> VideoPackage:
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

    try:
        from debug import dprint

        dprint("brain", "generate_script backend", "openai", f"model={_llm_model(settings)!r}")
    except Exception:
        pass

    if on_llm_task:
        on_llm_task("llm_generate", 10, "Calling OpenAI (API mode)…")
    client = build_openai_client_from_settings(settings)
    raw = client.chat_completion_text(
        model=_llm_model(settings),
        system=SCRIPT_JSON_SYSTEM,
        user=prompt,
        json_mode=True,
    )
    if on_llm_task:
        on_llm_task("llm_generate", 100, "Script JSON received")
    return video_package_from_llm_output(raw, video_format=str(video_format or "news"))


def expand_custom_video_instructions_openai(
    *,
    settings: AppSettings,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> str:
    if on_llm_task:
        on_llm_task("llm_generate", 5, "Expanding brief (OpenAI)…")
    client = build_openai_client_from_settings(settings)
    p = get_personality_by_id(personality_id)
    user = (
        f"Video format: {video_format}\n"
        f"Tone: {p.label}\n\n"
        "Expand and tighten this creator brief into a richer creative brief (plain text, no JSON):\n\n"
        f"{raw_instructions.strip()[:8000]}"
    )
    out = client.chat_completion_text(
        model=_llm_model(settings),
        system="You help short-form video creators. Output improved plain-text instructions only.",
        user=user,
        json_mode=False,
    )
    if on_llm_task:
        on_llm_task("llm_generate", 100, "Brief expanded")
    return (out or "").strip() or raw_instructions.strip()


def expand_custom_field_text_openai(
    *,
    settings: AppSettings,
    field_label: str,
    seed: str,
) -> str:
    client = build_openai_client_from_settings(settings)
    user = f"Field: {field_label}\n\nImprove this text (plain output only, no quotes):\n\n{(seed or '').strip()[:12000]}"
    return client.chat_completion_text(
        model=_llm_model(settings),
        system="You improve UI field text for a video app. Output only the revised text.",
        user=user,
        json_mode=False,
    ).strip()


TOPIC_GROUNDING_BATCH_JSON_SYSTEM = (
    "Return ONLY valid JSON — no Markdown fences or commentary.\n"
    'Use top-level object key "notes" mapping each normalized lowercase topic tag '
    "to one plain-text grounding line (~200 chars max)."
)


def generate_topic_tag_grounding_notes_openai(
    *,
    settings: AppSettings,
    tag_pairs: Sequence[tuple[str, str]],
    video_format: str,
    sibling_displays: Sequence[str],
    seed_notes_by_norm: Mapping[str, str] | None = None,
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    pairs = [(str(n).strip().lower(), str(d).strip()) for n, d in tag_pairs if str(n or "").strip()]
    if not pairs:
        return {}, ()
    allowed_all = frozenset(n for n, _ in pairs)
    seeds = dict(seed_notes_by_norm or {})
    chunks = topic_grounding_pair_chunks(pairs)
    n_chunks = len(chunks)
    merged_notes: dict[str, str] = {}
    client = build_openai_client_from_settings(settings)

    def _scale_api_progress(chunk_idx: int, inner_pct: int, msg: str) -> None:
        if on_llm_task is None:
            return
        inner_f = max(0.0, min(1.0, inner_pct / 100.0))
        overall = int(100 * (chunk_idx + inner_f) / n_chunks)
        if chunk_idx >= n_chunks - 1 and inner_pct >= 100:
            overall = 100
        on_llm_task("llm_generate", max(0, min(100, overall)), f"Tags batch {chunk_idx + 1}/{n_chunks}: {msg}")

    for idx, chunk_pairs in enumerate(chunks):
        _scale_api_progress(idx, 5, "Topic grounding (API)…")
        user = _prompt_topic_tag_grounding_batch(
            chunk_pairs,
            video_format,
            sibling_displays=sibling_displays,
            seed_notes_by_norm=seeds,
        )
        raw = client.chat_completion_text(
            model=_llm_model(settings),
            system=TOPIC_GROUNDING_BATCH_JSON_SYSTEM,
            user=user,
            json_mode=True,
        )
        allowed_chunk = frozenset(n for n, _ in chunk_pairs)
        notes, _m = parse_topic_grounding_llm_json(raw, allowed_normalized_tags=allowed_chunk)
        merged_notes.update(notes)
        _scale_api_progress(idx, 100, "batch received")

    missing_final = tuple(sorted(t for t in allowed_all if t not in merged_notes))
    return merged_notes, missing_final


CHARACTER_JSON_SYSTEM = (
    "Return ONLY valid JSON for one character profile. Keys: name, identity, visual_style, "
    "negatives, use_default_voice (boolean). No markdown or commentary."
)


def generate_character_from_preset_openai(
    *,
    settings: AppSettings,
    preset: CharacterAutoPreset,
    extra_notes: str = "",
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> GeneratedCharacterFields:
    """Same JSON contract as :func:`src.content.brain.generate_character_from_preset_llm` via OpenAI."""
    notes = (extra_notes or "").strip()
    notes_block = f"Extra notes from the user (optional):\n{notes}\n" if notes else ""
    arch = (preset.llm_directive or "").strip() or "Original short-form video host."
    user = (
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
    if on_llm_task:
        on_llm_task("llm_generate", 10, "Calling OpenAI for character JSON…")
    client = build_openai_client_from_settings(settings)
    raw = client.chat_completion_text(
        model=_llm_model(settings),
        system=CHARACTER_JSON_SYSTEM,
        user=user,
        json_mode=True,
    )
    if on_llm_task:
        on_llm_task("llm_generate", 100, "Character JSON received")
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
