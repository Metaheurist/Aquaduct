"""Unit tests for LLM-assisted field expansion (no real model load)."""

from __future__ import annotations


def test_expand_custom_field_text_strips_code_fence(monkeypatch):
    from src import brain as b

    def fake_gen(model_id: str, prompt: str, **kwargs):
        return "```\nExpanded identity text here.\n```"

    monkeypatch.setattr(b, "_generate_with_transformers", fake_gen)
    out = b.expand_custom_field_text(model_id="dummy/Dummy", field_label="Identity", seed="host")
    assert "Expanded identity" in out
    assert "```" not in out


def test_expand_custom_field_text_strips_quotes(monkeypatch):
    from src import brain as b

    def fake_gen(model_id: str, prompt: str, **kwargs):
        return '"Single paragraph output."'

    monkeypatch.setattr(b, "_generate_with_transformers", fake_gen)
    out = b.expand_custom_field_text(model_id="dummy/Dummy", field_label="Negatives", seed="")
    assert out.startswith("Single paragraph")
