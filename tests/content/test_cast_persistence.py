"""Phase 8 tests for auto-cast persistence and Character parity.

These tests cover:

- ``cast_to_characters`` produces full :class:`Character` objects with the same fields as
  the Characters tab (identity, visual_style, negatives, voice_instruction).
- IDs are deterministic per (name, video_format, headline_seed), so re-running the same
  cast does not duplicate entries.
- ``merge_cast_into_store`` upserts into the global ``characters.json`` without removing
  existing entries.
- ``fallback_cast_for_show`` includes ``voice_instruction`` for every video format.
- ``cast_to_ephemeral_character`` propagates ``voice_instruction`` from the cast.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.content import characters_store as cs
from src.content.characters_store import (
    Character,
    cast_to_characters,
    cast_to_ephemeral_character,
    fallback_cast_for_show,
    merge_cast_into_store,
)


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path) -> Path:
    """Redirect ``characters_path()`` to a tmp file so tests don't touch real user data."""
    target = tmp_path / "characters.json"

    def _fake_path() -> Path:
        return target

    monkeypatch.setattr(cs, "characters_path", _fake_path)
    return tmp_path


def _sample_cast() -> list[dict[str, str]]:
    return [
        {
            "name": "Lead",
            "role": "Host",
            "identity": "Sharp, dry host who guides the cold open.",
            "visual_style": "9:16 vertical, neon HUD",
            "negatives": "no slurs",
            "voice_instruction": "mid-30s neutral host, brisk pace",
        },
        {
            "name": "Foil",
            "role": "Sidekick",
            "identity": "Reactive comic relief, slow burn.",
            "visual_style": "rubber-hose toon style",
            "negatives": "no slurs",
            "voice_instruction": "slightly nasal, deadpan, half a beat slower",
        },
    ]


def test_cast_to_characters_full_parity_with_characters_tab() -> None:
    chars = cast_to_characters(cast=_sample_cast(), video_format="cartoon", headline_seed="abc")
    assert len(chars) == 2
    for ch in chars:
        assert isinstance(ch, Character)
        assert ch.name
        assert ch.identity
        assert ch.visual_style
        assert ch.negatives
        assert ch.voice_instruction
        assert ch.id and len(ch.id) >= 8
        assert ch.use_default_voice is True
        assert ch.reference_image_rel == ""


def test_cast_to_characters_role_prepended_to_identity_when_missing() -> None:
    cast = [{"name": "X", "role": "Narrator", "identity": "calm storyteller"}]
    chars = cast_to_characters(cast=cast, video_format="creepypasta", headline_seed="seed")
    assert chars[0].identity.startswith("Narrator: calm storyteller")


def test_cast_to_characters_role_only_when_no_identity() -> None:
    cast = [{"name": "X", "role": "Narrator"}]
    chars = cast_to_characters(cast=cast, video_format="news", headline_seed="seed")
    assert chars[0].identity == "Narrator"


def test_cast_to_characters_deterministic_ids() -> None:
    cast = _sample_cast()
    a = cast_to_characters(cast=cast, video_format="cartoon", headline_seed="run-1")
    b = cast_to_characters(cast=cast, video_format="cartoon", headline_seed="run-1")
    assert [c.id for c in a] == [c.id for c in b]


def test_cast_to_characters_ids_differ_per_format() -> None:
    a = cast_to_characters(cast=_sample_cast(), video_format="cartoon", headline_seed="seed")
    b = cast_to_characters(cast=_sample_cast(), video_format="news", headline_seed="seed")
    assert {c.id for c in a}.isdisjoint({c.id for c in b})


def test_cast_to_characters_skips_unnamed_entries() -> None:
    cast = [{"name": "", "identity": "x"}, {"name": "  ", "identity": "y"}, {"name": "Real", "identity": "z"}]
    chars = cast_to_characters(cast=cast, video_format="news", headline_seed="seed")
    assert len(chars) == 1
    assert chars[0].name == "Real"


def test_merge_cast_into_store_creates_file_and_persists(isolated_data_dir: Path) -> None:
    persisted = merge_cast_into_store(
        cast=_sample_cast(), video_format="cartoon", headline_seed="run-1"
    )
    assert len(persisted) == 2
    raw = json.loads((isolated_data_dir / "characters.json").read_text(encoding="utf-8"))
    names = sorted(c["name"] for c in raw)
    assert names == ["Foil", "Lead"]


def test_merge_cast_is_idempotent(isolated_data_dir: Path) -> None:
    merge_cast_into_store(cast=_sample_cast(), video_format="cartoon", headline_seed="run-1")
    merge_cast_into_store(cast=_sample_cast(), video_format="cartoon", headline_seed="run-1")
    raw = json.loads((isolated_data_dir / "characters.json").read_text(encoding="utf-8"))
    assert len(raw) == 2


def test_merge_cast_preserves_existing_entries(isolated_data_dir: Path) -> None:
    existing = Character(
        id="ff" * 8 + "00" * 8,
        name="Hand-authored",
        identity="kept",
        visual_style="kept",
        negatives="kept",
        reference_image_rel="",
        use_default_voice=True,
        pyttsx3_voice_id="",
        kokoro_voice="",
        voice_instruction="",
        elevenlabs_voice_id="",
    )
    cs.save_all([existing])
    merge_cast_into_store(cast=_sample_cast(), video_format="cartoon", headline_seed="run-1")
    raw = json.loads((isolated_data_dir / "characters.json").read_text(encoding="utf-8"))
    names = sorted(c["name"] for c in raw)
    assert names == ["Foil", "Hand-authored", "Lead"]


def test_merge_cast_empty_input_returns_empty(isolated_data_dir: Path) -> None:
    persisted = merge_cast_into_store(cast=[], video_format="news", headline_seed="seed")
    assert persisted == []
    assert not (isolated_data_dir / "characters.json").exists()


@pytest.mark.parametrize(
    "video_format",
    ["news", "explainer", "creepypasta", "health_advice", "cartoon", "unhinged"],
)
def test_fallback_cast_for_show_includes_voice_instruction(video_format: str) -> None:
    cast = fallback_cast_for_show(
        video_format=video_format, topic_tags=["tag-a", "tag-b"], headline_seed="seed"
    )
    assert cast, f"{video_format} returned empty cast"
    for member in cast:
        assert member.get("voice_instruction"), f"{video_format} missing voice_instruction"


def test_cast_to_ephemeral_character_carries_voice_instruction_for_narrator_formats() -> None:
    cast = fallback_cast_for_show(
        video_format="creepypasta", topic_tags=["folk-horror"], headline_seed="seed"
    )
    ch = cast_to_ephemeral_character(cast=cast, video_format="creepypasta")
    assert ch.voice_instruction


def test_cast_to_ephemeral_character_aggregates_voice_for_multi_character() -> None:
    cast = fallback_cast_for_show(
        video_format="cartoon", topic_tags=["bit"], headline_seed="seed"
    )
    ch = cast_to_ephemeral_character(cast=cast, video_format="cartoon")
    assert "Cast voice directions" in ch.voice_instruction
    for member in cast:
        assert member["name"] in ch.voice_instruction
