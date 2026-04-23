from __future__ import annotations

import pytest

from src.content.brain import _extract_json, _llm_max_input_tokens_cap, enforce_arc, generate_script


def test_llm_max_input_tokens_cap_respects_env(monkeypatch):
    class _Tok:
        model_max_length = 8192

    monkeypatch.delenv("AQUADUCT_LLM_MAX_INPUT_TOKENS", raising=False)
    assert _llm_max_input_tokens_cap(_Tok()) == 4096

    monkeypatch.setenv("AQUADUCT_LLM_MAX_INPUT_TOKENS", "2048")
    assert _llm_max_input_tokens_cap(_Tok()) == 2048


def test_llm_max_input_tokens_cap_min_with_tokenizer_max(monkeypatch):
    class _Tok:
        model_max_length = 2048

    monkeypatch.delenv("AQUADUCT_LLM_MAX_INPUT_TOKENS", raising=False)
    assert _llm_max_input_tokens_cap(_Tok()) == 2048


def test_extract_json_from_fenced_block():
    d = _extract_json(
        """hello
```json
{"title":"t","description":"d","hashtags":[],"hook":"h","segments":[],"cta":"c"}
```
"""
    )
    assert d["title"] == "t"


def test_generate_script_custom_brief_uses_creative_prompt(monkeypatch):
    import src.content.brain as brain_mod

    captured: dict[str, str] = {}

    def fake_gen(model_id: str, prompt: str, **kwargs):
        captured["prompt"] = prompt
        return (
            '{"title":"T","description":"D","hashtags":["#A"],"hook":"H",'
            '"segments":[{"narration":"N","visual_prompt":"V","on_screen_text":"O"}],"cta":"C"}'
        )

    monkeypatch.setattr(brain_mod, "_generate_with_transformers", fake_gen)
    pkg = brain_mod.generate_script(
        model_id="x",
        items=[{"title": "Synthetic", "url": "", "source": "custom"}],
        creative_brief="My creative angle for the video.",
        video_format="explainer",
    )
    assert "My creative angle" in captured["prompt"]
    assert "Creative brief" in captured["prompt"]
    assert pkg.title == "T"


def test_extract_json_from_inline_object():
    d = _extract_json('{"a":1, "b":2}')
    assert d == {"a": 1, "b": 2}


@pytest.mark.parametrize("pid,expected_phrase", [
    ("hype", "stop scrolling"),
    ("skeptical", "honest read"),
    ("urgent", "moving fast"),
])
def test_generate_script_fallback_tone_changes(monkeypatch, pid, expected_phrase):
    # Force LLM path to raise so fallback triggers
    import src.content.brain as brain_mod

    monkeypatch.setattr(brain_mod, "_generate_with_transformers", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    pkg = generate_script(model_id="x", items=[{"title": "Tool X released", "url": "u", "source": "s"}], personality_id=pid)
    assert expected_phrase.lower() in pkg.hook.lower()


def test_enforce_arc_injects_missing_beats():
    from src.content.brain import ScriptSegment, VideoPackage

    pkg = VideoPackage(
        title="t",
        description="d",
        hashtags=["#AI"],
        hook="Stop scrolling—new tool dropped.",
        segments=[
            ScriptSegment(narration="Point one.", visual_prompt="v1", on_screen_text="ONE"),
            ScriptSegment(narration="Point two.", visual_prompt="v2", on_screen_text="TWO"),
        ],
        cta="Follow for more.",
    )
    out = enforce_arc(pkg)
    assert len(out.segments) >= len(pkg.segments)
    txt = " ".join(s.narration.lower() for s in out.segments)
    assert "context" in txt or "what it is" in txt
    assert "why it matters" in txt or "why" in txt

