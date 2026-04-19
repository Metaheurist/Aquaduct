"""Effects template registry (no Qt)."""

from __future__ import annotations

from src.settings.effects_presets import EFFECT_PRESETS, find_best_preset_for_effects, preset_by_id


def test_preset_by_id():
    assert preset_by_id("effects_balanced") is not None
    assert preset_by_id("effects_balanced").title == "Balanced (default)"  # type: ignore[union-attr]
    assert preset_by_id("") is None
    assert preset_by_id("nope") is None


def test_find_best_matches_balanced_defaults():
    p = preset_by_id("effects_balanced")
    assert p is not None
    got = find_best_preset_for_effects(
        quality_retries=p.quality_retries,
        enable_motion=p.enable_motion,
        transition_strength=p.transition_strength,
        xfade_transition=p.xfade_transition,
        seed_base=p.seed_base,
        audio_polish=p.audio_polish,
        music_ducking=p.music_ducking,
        music_ducking_amount=p.music_ducking_amount,
        music_fade_s=p.music_fade_s,
        sfx_mode=p.sfx_mode,
    )
    assert got == "effects_balanced"


def test_find_best_returns_empty_when_seed_differs():
    p = preset_by_id("effects_balanced")
    assert p is not None
    got = find_best_preset_for_effects(
        quality_retries=p.quality_retries,
        enable_motion=p.enable_motion,
        transition_strength=p.transition_strength,
        xfade_transition=p.xfade_transition,
        seed_base=42,
        audio_polish=p.audio_polish,
        music_ducking=p.music_ducking,
        music_ducking_amount=p.music_ducking_amount,
        music_fade_s=p.music_fade_s,
        sfx_mode=p.sfx_mode,
    )
    assert got == ""


def test_all_presets_have_unique_ids():
    ids = [p.id for p in EFFECT_PRESETS]
    assert len(ids) == len(set(ids))
