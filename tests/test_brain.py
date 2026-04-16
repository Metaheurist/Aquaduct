from __future__ import annotations

import pytest

from src.brain import _extract_json, enforce_arc, generate_script


def test_extract_json_from_fenced_block():
    d = _extract_json(
        """hello
```json
{"title":"t","description":"d","hashtags":[],"hook":"h","segments":[],"cta":"c"}
```
"""
    )
    assert d["title"] == "t"


def test_extract_json_from_inline_object():
    d = _extract_json('{"a":1, "b":2}')
    assert d == {"a": 1, "b": 2}


@pytest.mark.parametrize("pid,expected_phrase", [
    ("hype", "insane"),
    ("skeptical", "believe the hype"),
    ("urgent", "Breaking"),
])
def test_generate_script_fallback_tone_changes(monkeypatch, pid, expected_phrase):
    # Force LLM path to raise so fallback triggers
    import src.brain as brain_mod

    monkeypatch.setattr(brain_mod, "_generate_with_transformers", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    pkg = generate_script(model_id="x", items=[{"title": "Tool X released", "url": "u", "source": "s"}], personality_id=pid)
    assert expected_phrase.lower() in pkg.hook.lower()


def test_enforce_arc_injects_missing_beats():
    from src.brain import ScriptSegment, VideoPackage

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

