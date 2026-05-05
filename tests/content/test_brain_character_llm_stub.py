"""Stub LLM outputs for character/cast generators — no transformer load."""

from __future__ import annotations

import json


def test_generate_character_from_preset_llm_parses_identity_tokens(monkeypatch):
    from src.content.brain import api as brain_api
    from src.content.character_presets import get_character_auto_preset_by_id

    preset = get_character_auto_preset_by_id("gen_z")
    assert preset is not None

    payload = {
        "name": "Riven Luxe",
        "identity": "Luxury host persona.",
        "visual_style": "minimal studio, soft key light",
        "negatives": "watermark",
        "use_default_voice": True,
        "gender": "woman",
        "ethnicity": "East Asian",
        "age_range": "late 20s",
    }

    def _fake_generate(*_args, **_kwargs):
        return json.dumps(payload)

    monkeypatch.setattr(brain_api, "_generate_with_transformers", _fake_generate)

    out = brain_api.generate_character_from_preset_llm(model_id="stub-model", preset=preset)
    assert out.name == "Riven Luxe"
    assert out.gender == "woman"
    assert out.ethnicity == "East Asian"
    assert out.age_range == "late 20s"


def test_generate_cast_from_storyline_llm_includes_identity_tokens(monkeypatch):
    from src.content.brain import api as brain_api

    blob = {
        "characters": [
            {
                "name": "A",
                "role": "Host",
                "identity": "Sharp analyst.",
                "visual_style": "news desk",
                "negatives": "",
                "voice_instruction": "Clear mid-pace.",
                "gender": "man",
                "ethnicity": "West African",
                "age_range": "40s",
            },
            {
                "name": "B",
                "role": "Foil",
                "identity": "Skeptic.",
                "visual_style": "bright cartoon",
                "negatives": "",
                "voice_instruction": "Dry.",
                "gender": "non-binary",
                "ethnicity": "",
                "age_range": "",
            },
        ]
    }

    def _fake_infer(*_args, **_kwargs):
        return json.dumps(blob)

    monkeypatch.setattr(brain_api, "_infer_text_with_optional_holder", _fake_infer)

    cast = brain_api.generate_cast_from_storyline_llm(
        model_id="stub",
        video_format="cartoon",
        storyline_title="T",
        storyline_text="Two hosts debate.",
        topic_tags=["tech"],
    )
    assert len(cast) == 2
    assert cast[0]["gender"] == "man"
    assert cast[0]["ethnicity"] == "West African"
    assert cast[1]["gender"] == "non-binary"
