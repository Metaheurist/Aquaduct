"""Unit tests for LLM-assisted field expansion (no real model load)."""

from __future__ import annotations


def test_expand_custom_field_text_strips_code_fence(monkeypatch):
    from src.content import brain as b

    def fake_gen(model_id: str, prompt: str, **kwargs):
        return "```\nExpanded identity text here.\n```"

    monkeypatch.setattr(b, "_generate_with_transformers", fake_gen)
    out = b.expand_custom_field_text(model_id="dummy/Dummy", field_label="Identity", seed="host")
    assert "Expanded identity" in out
    assert "```" not in out


def test_expand_custom_video_instructions_returns_trimmed_text(monkeypatch):
    from src.content import brain as b

    def fake_infer(model_id: str, prompt: str, **kwargs):
        assert "User's raw notes" in prompt
        assert "Rough notes about my video" in prompt
        return "  \nExpanded creative brief.\n"

    monkeypatch.setattr(b, "_infer_text_with_optional_holder", fake_infer)
    out = b.expand_custom_video_instructions(
        model_id="dummy/Dummy",
        raw_instructions="Rough notes about my video",
        video_format="news",
        personality_id="neutral",
    )
    assert out == "Expanded creative brief."


def test_expand_custom_field_text_strips_quotes(monkeypatch):
    from src.content import brain as b

    def fake_gen(model_id: str, prompt: str, **kwargs):
        return '"Single paragraph output."'

    monkeypatch.setattr(b, "_generate_with_transformers", fake_gen)
    out = b.expand_custom_field_text(model_id="dummy/Dummy", field_label="Negatives", seed="")
    assert out.startswith("Single paragraph")
