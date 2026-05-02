"""Phase 4/7 tests for ``expand_scenes_via_llm`` in ``src/render/scene_prompts.py``.

These tests focus exclusively on the LLM-expansion path: when a script
produces fewer segments than the requested ``n_scenes``, the builder calls a
caller-supplied ``invoke_llm`` once to top up the missing beats. We never
touch the real LLM here -- the callable is a stub.
"""
from __future__ import annotations

from src.render.scene_prompts import (
    SceneSpec,
    expand_scenes_via_llm,
    specs_to_prompts,
)


def test_no_op_when_already_at_target() -> None:
    specs = [SceneSpec(prompt=f"prompt {i}", role="segment", source_index=i) for i in range(3)]
    out = expand_scenes_via_llm(
        specs,
        target_count=3,
        video_format="creepypasta",
        character_context=None,
        invoke_llm=lambda _p: "should not be called",
    )
    assert [s.prompt for s in out] == [s.prompt for s in specs]


def test_no_op_when_invoke_llm_missing() -> None:
    specs = [SceneSpec(prompt="solo scene", role="segment", source_index=0)]
    out = expand_scenes_via_llm(
        specs,
        target_count=4,
        video_format="news",
        character_context=None,
        invoke_llm=None,
    )
    assert out == specs


def test_appends_until_target_count() -> None:
    specs = [SceneSpec(prompt="opening shot", role="hook", source_index=-1)]

    def fake_llm(_prompt: str) -> str:
        return "\n".join([
            "second beat in the warehouse, slow dolly forward",
            "third beat with a sudden noise, wide angle reaction",
            "final beat, hand reaching into shadow",
        ])

    out = expand_scenes_via_llm(
        specs,
        target_count=4,
        video_format="creepypasta",
        character_context=None,
        invoke_llm=fake_llm,
    )
    assert len(out) == 4
    assert out[0] == specs[0]
    expanded = [s for s in out if s.role == "expanded"]
    assert len(expanded) == 3


def test_expanded_prompts_strip_bullets_and_numbers() -> None:
    specs = [SceneSpec(prompt="seed", role="segment", source_index=0)]

    def fake_llm(_prompt: str) -> str:
        return "\n".join([
            "1) numbered prompt with a misty corridor",
            "- bullet prompt with a flickering bulb",
            "* asterisk prompt, neon city alley",
        ])

    out = expand_scenes_via_llm(
        specs,
        target_count=4,
        video_format="cartoon",
        character_context=None,
        invoke_llm=fake_llm,
    )
    expanded_prompts = [s.prompt for s in out if s.role == "expanded"]
    assert all(not p.lstrip().startswith(("-", "*", "1", "2", "3")) for p in expanded_prompts)


def test_expansion_uses_cast_names_in_prompt() -> None:
    specs = [SceneSpec(prompt="seed", role="segment", source_index=0)]
    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "extra scene with the cast"

    expand_scenes_via_llm(
        specs,
        target_count=2,
        video_format="cartoon",
        character_context="- Ava (lead): short brown hair\n- Elijah (foil): tall, gloomy",
        invoke_llm=fake_llm,
    )
    assert len(captured) == 1
    seed_prompt = captured[0]
    assert "Ava" in seed_prompt
    assert "Elijah" in seed_prompt


def test_expansion_failure_falls_back_to_existing_specs() -> None:
    specs = [SceneSpec(prompt="solo", role="segment", source_index=0)]

    def angry_llm(_prompt: str) -> str:
        raise RuntimeError("boom")

    out = expand_scenes_via_llm(
        specs,
        target_count=5,
        video_format="news",
        character_context=None,
        invoke_llm=angry_llm,
    )
    assert out == specs


def test_target_count_clamped_to_scene_count_max() -> None:
    from src.render.scene_prompts import SCENE_COUNT_MAX

    specs = [SceneSpec(prompt=f"s{i}", role="segment", source_index=i) for i in range(3)]

    def fake_llm(_prompt: str) -> str:
        return "\n".join(f"extra {i}" for i in range(99))

    out = expand_scenes_via_llm(
        specs,
        target_count=999,
        video_format="news",
        character_context=None,
        invoke_llm=fake_llm,
    )
    assert len(out) <= SCENE_COUNT_MAX


def test_specs_to_prompts_drops_empty() -> None:
    specs = [
        SceneSpec(prompt="kept", role="segment", source_index=0),
        SceneSpec(prompt="", role="expanded", source_index=-1),
        SceneSpec(prompt="also kept", role="cta", source_index=2),
    ]
    assert specs_to_prompts(specs) == ["kept", "also kept"]
