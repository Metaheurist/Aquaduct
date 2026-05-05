from __future__ import annotations

from src.core.config import AppSettings
from dataclasses import replace

from src.content.characters_store import (
    Character,
    character_context_for_brain,
    load_all,
    merged_character_for_pipeline,
    new_character,
    resolve_active_character,
    resolve_character_for_pipeline,
    save_all,
    upsert,
)
from src.content.brain import _prompt_for_items
from src.content.personalities import get_personality_by_id


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


def test_character_roundtrip_identity_tokens(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Tok")
    c2 = Character(
        id=c.id,
        name="Tok",
        identity="host",
        visual_style="studio",
        negatives="",
        gender="woman",
        ethnicity="East Asian",
        age_range="30s",
        use_default_voice=True,
    )
    save_all([c2])
    got = load_all()[0]
    assert got.gender == "woman"
    assert got.ethnicity == "East Asian"
    assert got.age_range == "30s"


def test_character_from_dict_missing_token_keys(patch_paths, tmp_repo_root):
    import json
    from src.content.characters_store import characters_path

    p = characters_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = [
        {
            "id": "a" * 16,
            "name": "Legacy",
            "identity": "x",
            "visual_style": "y",
            "negatives": "",
        }
    ]
    p.write_text(json.dumps(raw), encoding="utf-8")
    got = load_all()[0]
    assert got.gender == ""
    assert got.ethnicity == ""
    assert got.age_range == ""


def test_resolve_active_character_ids_order(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="First")
    d = new_character(name="Second")
    save_all([c, d])
    s = AppSettings(active_character_ids=(d.id, c.id))
    from src.content.characters_store import resolve_active_characters

    ordered = resolve_active_characters(s)
    assert len(ordered) == 2
    assert ordered[0].id == d.id


def test_resolve_character_for_pipeline_merges_multiple_active(patch_paths, tmp_repo_root):
    save_all([])
    c = new_character(name="Lead")
    d = new_character(name="Side")
    save_all([c, d])
    got = resolve_character_for_pipeline(
        AppSettings(active_character_ids=(c.id, d.id)),
        video_format="cartoon",
    )
    assert "Cast:" in got.name
    assert got.id == c.id
    assert "Lead" in got.identity and "Side" in got.identity


def test_merged_character_for_pipeline_lead_voice_fields(patch_paths, tmp_repo_root):
    lead = new_character(name="L")
    lead = replace(
        lead,
        kokoro_voice="af_lead",
        use_default_voice=False,
        elevenlabs_voice_id="el_x",
        reference_image_rel="characters/x/p.png",
        gender="woman",
    )
    side = replace(new_character(name="S"), identity="foil")
    m = merged_character_for_pipeline([lead, side], video_format="unhinged")
    assert m.kokoro_voice == "af_lead"
    assert m.use_default_voice is False
    assert m.elevenlabs_voice_id == "el_x"
    assert m.reference_image_rel == "characters/x/p.png"
    assert m.gender == "woman"
    assert "foil" in m.identity
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
    # Saved characters are only used when explicitly selected.
    assert got.id not in (c.id, d.id)


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
        visual_style="darkUI",
        negatives="gore",
        gender="woman",
        ethnicity="South Asian",
        age_range="40s",
        use_default_voice=True,
    )
    text = character_context_for_brain(c)
    assert "Zed" in text
    assert "calm reviewer" in text
    assert "darkUI" in text
    assert "gore" in text
    assert "Identity tokens" in text
    assert "woman" in text and "South Asian" in text


def test_character_context_for_brain_includes_reference_note(patch_paths, tmp_repo_root):
    # Use ``config.get_paths()`` (module attribute) so monkeypatch replaces it; a top-level
    # ``from src.core.config import get_paths`` would keep the pre-patch function object.
    from src.core import config

    c = new_character(name="WithRef")
    rel = f"characters/{c.id}/portrait.png"
    p = config.get_paths().data_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x05\x01\x02\xcf\xa0.\xcd\x00\x00\x00\x00IEND\xaeB`\x82")
    c2 = replace(c, reference_image_rel=rel)
    text = character_context_for_brain(c2)
    assert "Canonical host reference portrait" in text


def test_prompt_for_items_character_block():
    pers = get_personality_by_id("neutral")
    ptext = _prompt_for_items(
        [{"title": "T", "url": "u", "source": "s"}],
        [],
        pers,
        character_context="Channel host: Zed",
    )
    assert "Channel host: Zed" in ptext
    assert "Character / host (mandatory" in ptext
