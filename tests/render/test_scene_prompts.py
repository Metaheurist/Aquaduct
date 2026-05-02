"""Phase 4 tests for ``src/render/scene_prompts.py``.

These tests are intentionally pure-Python -- the module never imports torch
or the brain LLM, so we can exercise diversity, character injection,
genre cues, headline-prefix removal, and LLM expansion without the heavy
runtime stack.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pytest

from src.render import scene_prompts as sp


@dataclass
class _StubSegment:
    narration: str = ""
    visual_prompt: str = ""
    on_screen_text: str = ""


@dataclass
class _StubPackage:
    title: str = ""
    hook: str = ""
    cta: str = ""
    segments: Sequence[Any] = ()


CHARACTER_CONTEXT_DUO = """\
Character name: Cast: Lead & Foil

Cast (mandatory):
- Lead (Host): commits to the bit
- Foil (Sidekick): reacts deadpan
"""

CHARACTER_CONTEXT_SOLO = """\
Character name: Mara Vex

Identity / channel persona (must stay consistent in narration and on-screen cues):
Narrator Mara Vex: calm storyteller, late-night campfire voice.
"""


def test_strip_noise_removes_negative_block() -> None:
    assert sp.strip_noise("foo bar  NEGATIVE: blurry, deformed") == "foo bar"


def test_cap_words_truncates() -> None:
    text = " ".join(["w"] * 80)
    assert len(sp.cap_words(text, n_words=40).split()) == 40


def test_no_title_prefix_for_news() -> None:
    pkg = _StubPackage(
        title="Top 10 Widgets - Blog",
        hook="Hook line",
        segments=[_StubSegment(narration="First beat about widgets", visual_prompt="vis")],
        cta="Subscribe",
    )
    specs = sp.build_scene_prompts(pkg=pkg, video_format="news")
    prompts = sp.specs_to_prompts(specs)
    assert prompts
    for p in prompts:
        assert "Top 10 Widgets" not in p


def test_cartoon_uses_visual_prompt_over_narration() -> None:
    pkg = _StubPackage(
        hook="meta hook",
        segments=[
            _StubSegment(
                narration="this should not appear",
                visual_prompt="bright stage with confetti",
            )
        ],
        cta="end card",
    )
    specs = sp.build_scene_prompts(pkg=pkg, video_format="cartoon")
    prompts = sp.specs_to_prompts(specs)
    assert any("confetti" in p for p in prompts)


def test_cast_names_are_injected_for_duo_format() -> None:
    pkg = _StubPackage(
        hook="cold open",
        segments=[
            _StubSegment(visual_prompt="kitchen scene"),
            _StubSegment(visual_prompt="hallway scene"),
            _StubSegment(visual_prompt="rooftop scene"),
        ],
        cta="end",
    )
    specs = sp.build_scene_prompts(
        pkg=pkg,
        video_format="cartoon",
        character_context=CHARACTER_CONTEXT_DUO,
    )
    prompts = sp.specs_to_prompts(specs)
    joined = " ".join(prompts)
    assert "Lead" in joined
    assert "Foil" in joined


def test_solo_narrator_name_injected_for_creepypasta() -> None:
    pkg = _StubPackage(
        hook="late at night",
        segments=[_StubSegment(visual_prompt="empty hallway"), _StubSegment(visual_prompt="lamp flicker")],
    )
    specs = sp.build_scene_prompts(
        pkg=pkg,
        video_format="creepypasta",
        character_context=CHARACTER_CONTEXT_SOLO,
    )
    prompts = sp.specs_to_prompts(specs)
    assert any("Mara Vex" in p for p in prompts)


def test_genre_motion_cues_are_format_specific() -> None:
    cre = sp._genre_motion_cues("creepypasta")
    cart = sp._genre_motion_cues("cartoon")
    news = sp._genre_motion_cues("news")
    assert any("fog" in c or "darkness" in c for c in cre)
    assert any("squash" in c or "whip" in c for c in cart)
    assert "slow push-in" in news


def test_genre_style_tail_includes_910_for_all_known_formats() -> None:
    for vf in ["news", "explainer", "cartoon", "unhinged", "creepypasta", "health_advice"]:
        tail = sp._genre_style_tail(vf)
        assert "9:16" in tail


def test_n_scenes_truncates_when_too_many() -> None:
    pkg = _StubPackage(
        hook="h",
        segments=[_StubSegment(narration=f"beat {i}", visual_prompt="v") for i in range(8)],
        cta="c",
    )
    specs = sp.build_scene_prompts(pkg=pkg, video_format="news", n_scenes=3)
    assert len(specs) == 3


def test_unique_starts_breaks_consecutive_duplicates() -> None:
    pkg = _StubPackage(
        segments=[
            _StubSegment(narration="opening shot of city skyline"),
            _StubSegment(narration="opening shot of city subway"),
            _StubSegment(narration="opening shot of city park"),
        ],
    )
    specs = sp.build_scene_prompts(pkg=pkg, video_format="news")
    heads = [" ".join(s.prompt.split()[:4]).lower() for s in specs]
    for i in range(len(heads) - 1):
        assert heads[i] != heads[i + 1], heads


def test_extract_character_names_handles_bullet_lines() -> None:
    names = sp._extract_character_names(CHARACTER_CONTEXT_DUO)
    assert "Lead" in names
    assert "Foil" in names


def test_extract_character_names_handles_solo_block() -> None:
    names = sp._extract_character_names(CHARACTER_CONTEXT_SOLO)
    assert names == ["Mara Vex"]


def test_extract_character_names_returns_empty_for_blank() -> None:
    assert sp._extract_character_names(None) == []
    assert sp._extract_character_names("") == []


def test_branding_affix_appears_once() -> None:
    pkg = _StubPackage(segments=[_StubSegment(visual_prompt="kitchen")])
    specs = sp.build_scene_prompts(
        pkg=pkg,
        video_format="news",
        branding_affix="palette: navy/gold, watermark BL",
    )
    prompts = sp.specs_to_prompts(specs)
    assert any("navy/gold" in p for p in prompts)


def test_fallback_uses_prompts_when_no_segments() -> None:
    pkg = _StubPackage(title="Empty", segments=[])
    specs = sp.build_scene_prompts(
        pkg=pkg,
        fallback_prompts=["wide street", "neon sign close-up"],
        video_format="news",
    )
    prompts = sp.specs_to_prompts(specs)
    assert any("wide street" in p for p in prompts)


def test_expand_scenes_via_llm_appends_new_lines() -> None:
    pkg = _StubPackage(
        segments=[_StubSegment(visual_prompt="kitchen scene")],
        cta="end",
    )
    specs = sp.build_scene_prompts(pkg=pkg, video_format="cartoon")
    assert len(specs) <= 2

    def fake_llm(prompt: str) -> str:
        return "\n".join(
            [
                "1. backstage rehearsal",
                "- spotlight failure",
                "- audience reaction",
                "* cast bow",
            ]
        )

    extended = sp.expand_scenes_via_llm(
        specs,
        target_count=4,
        video_format="cartoon",
        character_context=None,
        invoke_llm=fake_llm,
    )
    assert len(extended) == 4
    expanded_texts = [s.prompt for s in extended[len(specs) :]]
    assert any("backstage" in p for p in expanded_texts)
    assert any("spotlight" in p for p in expanded_texts)
    assert all("1." not in p[:4] for p in expanded_texts)
    assert all("- " not in p[:4] for p in expanded_texts)


def test_expand_scenes_no_op_when_already_enough() -> None:
    specs = [
        sp.SceneSpec(prompt="a", role="hook", source_index=-1),
        sp.SceneSpec(prompt="b", role="segment", source_index=0),
        sp.SceneSpec(prompt="c", role="segment", source_index=1),
    ]

    def boom(prompt: str) -> str:
        raise AssertionError("invoked despite enough specs")

    out = sp.expand_scenes_via_llm(
        specs,
        target_count=3,
        video_format="news",
        character_context=None,
        invoke_llm=boom,
    )
    assert [s.prompt for s in out] == ["a", "b", "c"]


def test_expand_scenes_swallows_llm_errors() -> None:
    specs = [sp.SceneSpec(prompt="only one", role="segment", source_index=0)]

    def explode(prompt: str) -> str:
        raise RuntimeError("network down")

    out = sp.expand_scenes_via_llm(
        specs,
        target_count=4,
        video_format="news",
        character_context=None,
        invoke_llm=explode,
    )
    assert out == specs


def test_specs_to_prompts_drops_empty_strings() -> None:
    specs = [
        sp.SceneSpec(prompt="real", role="segment", source_index=0),
        sp.SceneSpec(prompt="", role="segment", source_index=1),
    ]
    assert sp.specs_to_prompts(specs) == ["real"]
