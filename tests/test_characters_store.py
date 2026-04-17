from __future__ import annotations

from src.config import AppSettings
from src.characters_store import (
    Character,
    character_context_for_brain,
    load_all,
    new_character,
    resolve_active_character,
    resolve_character_for_pipeline,
    save_all,
    upsert,
)
from src.brain import _prompt_for_items
from src.personalities import get_personality_by_id


def test_character_roundtrip(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Alpha")
    c2 = Character(
        id=c.id,
        name="Alpha",
        identity="tech host",
        visual_style="neon studio",
        negatives="blur",
        use_default_voice=False,
        pyttsx3_voice_id="HKEY_abc",
        kokoro_voice="af_sky",
        elevenlabs_voice_id="el_voice_1",
    )
    save_all(upsert(load_all(), c2))
    loaded = load_all()
    assert len(loaded) == 1
    assert loaded[0].name == "Alpha"
    assert loaded[0].visual_style == "neon studio"
    assert loaded[0].pyttsx3_voice_id == "HKEY_abc"
    assert loaded[0].elevenlabs_voice_id == "el_voice_1"


def test_resolve_active_character(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Beta")
    save_all([c])
    s = AppSettings(active_character_id=c.id)
    got = resolve_active_character(s)
    assert got is not None
    assert got.id == c.id
    assert resolve_active_character(AppSettings(active_character_id="")) is None


def test_resolve_character_for_pipeline_ephemeral_when_empty(patch_paths, tmp_repo_root):
    save_all([])
    s = AppSettings(active_character_id="")
    got = resolve_character_for_pipeline(
        s,
        video_format="unhinged",
        topic_tags=["sketch"],
        headline_seed="Test headline",
    )
    assert got.name
    ctx = character_context_for_brain(got)
    assert "sketch" in ctx or "cynical" in got.identity.lower()


def test_resolve_character_for_pipeline_first_saved_when_no_active(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Zebra")
    d = new_character(name="Alpha")
    save_all([c, d])
    got = resolve_character_for_pipeline(AppSettings(active_character_id=""), video_format="news")
    assert got.id == d.id


def test_resolve_character_for_pipeline_prefers_active(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Pick")
    d = new_character(name="Other")
    save_all([c, d])
    got = resolve_character_for_pipeline(AppSettings(active_character_id=c.id), video_format="news")
    assert got.id == c.id


def test_character_context_for_brain():
    c = Character(
        id="a" * 16,
        name="Zed",
        identity="calm reviewer",
        visual_style="dark UI",
        negatives="gore",
        use_default_voice=True,
    )
    text = character_context_for_brain(c)
    assert "Zed" in text
    assert "calm reviewer" in text
    assert "dark UI" in text
    assert "gore" in text


def test_prompt_for_items_character_block():
    pers = get_personality_by_id("neutral")
    ptext = _prompt_for_items(
        [{"title": "T", "url": "u", "source": "s"}],
        [],
        pers,
        character_context="Channel host: Zed",
    )
    assert "Channel host: Zed" in ptext
    assert "Character / host identity" in ptext
