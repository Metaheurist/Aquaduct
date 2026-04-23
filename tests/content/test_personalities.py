from __future__ import annotations

from src.content.personalities import get_personality_by_id, get_personality_presets
from src.speech.tts_text import (
    merge_moss_character_and_run_personality,
    moss_style_instruction_for_personality,
    shape_tts_text,
)


def test_personality_ids_unique():
    presets = get_personality_presets()
    ids = [p.id for p in presets]
    assert len(ids) == len(set(ids))


def test_get_personality_by_id_fallback():
    p = get_personality_by_id("does-not-exist")
    assert p is not None
    assert p.id in {pp.id for pp in get_personality_presets()}


def test_shape_tts_text_chunks_long_sentences():
    text = "This is a very long sentence that should be split into smaller chunks so the TTS pacing sounds better and more natural."
    shaped = shape_tts_text(text, personality_id="urgent")
    assert shaped
    assert ("\n" in shaped) or ("…" in shaped)


def test_shape_tts_comedic_uses_shorter_chunks_than_neutral():
    words = [f"w{i}" for i in range(40)]
    text = " ".join(words) + "."
    comedic = shape_tts_text(text, personality_id="comedic")
    neutral = shape_tts_text(text, personality_id="neutral")
    assert comedic.count("\n") >= neutral.count("\n")


def test_moss_style_instruction_mentions_comedic():
    s = moss_style_instruction_for_personality("comedic")
    assert "Comedic" in s or "comedic" in s.lower()
    assert "joke" in s.lower() or "humor" in s.lower() or "Light" in s


def test_merge_moss_appends_run_personality():
    m = merge_moss_character_and_run_personality("A young woman, raspy voice.", "hype")
    assert m
    assert "A young woman" in m
    assert "Run personality" in m
    assert "Hype" in m or "hype" in m.lower()

