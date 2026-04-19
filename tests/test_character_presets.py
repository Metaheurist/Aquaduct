from src.character_presets import (
    coerce_generated_character_fields,
    extract_first_json_object,
    get_character_auto_preset_by_id,
    get_character_auto_presets,
)


def test_character_presets_cover_key_archetypes():
    ids = {p.id for p in get_character_auto_presets()}
    assert "unhinged_comedy" in ids
    assert "gen_z" in ids
    assert len(get_character_auto_presets()) >= 8


def test_get_character_auto_preset_by_id():
    p = get_character_auto_preset_by_id("unhinged_comedy")
    assert p is not None
    assert "satire" in p.llm_directive.lower() or "chaotic" in p.llm_directive.lower()
    assert get_character_auto_preset_by_id("nosuch") is None


def test_extract_first_json_object():
    raw = 'Here you go:\n```json\n{"name": "X", "identity": "a", "visual_style": "v", "negatives": "n", "use_default_voice": true}\n```'
    d = extract_first_json_object(raw)
    assert d == {
        "name": "X",
        "identity": "a",
        "visual_style": "v",
        "negatives": "n",
        "use_default_voice": True,
    }


def test_coerce_generated_character_fields():
    g = coerce_generated_character_fields(
        {
            "name": "Pat",
            "identity": "Host",
            "visual_style": "Neon",
            "negatives": "blur",
            "use_default_voice": False,
        }
    )
    assert g is not None
    assert g.name == "Pat"
    assert g.use_default_voice is False


def test_coerce_requires_name_and_some_content():
    assert coerce_generated_character_fields({"name": "", "identity": "x", "visual_style": ""}) is None
    assert coerce_generated_character_fields({"name": "A", "identity": "", "visual_style": ""}) is None
