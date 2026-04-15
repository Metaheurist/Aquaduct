from __future__ import annotations

import pytest

from src.brain import _extract_json, generate_script


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

