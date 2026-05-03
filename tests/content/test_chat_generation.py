from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch

from src.content.brain import (
    _eos_token_id_candidates,
    _generate_with_loaded_causal_lm,
    _pipeline_prompt_body_for_chat_template,
)


def test_eos_candidates_includes_base() -> None:
    tok = MagicMock()
    tok.eos_token_id = 9
    tok.convert_tokens_to_ids = MagicMock(return_value=-1)
    ids = _eos_token_id_candidates(tok)
    assert 9 in ids


def test_eos_candidates_adds_known_extra_tokens() -> None:
    tok = MagicMock()
    tok.eos_token_id = 1

    def ctok(t: str) -> int:
        return 128 if t == "<|eot_id|>" else -1

    tok.convert_tokens_to_ids = MagicMock(side_effect=ctok)
    ids = _eos_token_id_candidates(tok)
    assert 128 in ids


def test_pipeline_prompt_body_strips_alpaca_wrappers() -> None:
    raw = "### Instruction:\nDo the thing.\n\n### Response:\n"
    assert _pipeline_prompt_body_for_chat_template(raw) == "Do the thing."


@pytest.mark.usefixtures("monkeypatch")
def test_pipeline_generate_calls_apply_chat_template_when_chat_template_set(monkeypatch) -> None:
    import src.content.brain as brain

    monkeypatch.delenv("AQUADUCT_PIPELINE_FORCE_ALPACA", raising=False)
    monkeypatch.setattr(brain, "_llm_max_input_tokens_cap", lambda *_a, **_k: 8192)
    monkeypatch.setattr(brain, "cuda_device_reported_by_torch", lambda: False)
    monkeypatch.setattr(brain, "dprint", lambda *a, **k: None)

    class _FakeStreamer:
        def __init__(self, *a, **k) -> None:
            pass

        def __iter__(self):
            return iter(())

    monkeypatch.setattr(
        "src.models.hf_transformers_imports.text_iterator_streamer_cls",
        lambda: _FakeStreamer,
    )

    tok = MagicMock()
    tok.chat_template = "{% mock %}"
    tok.eos_token_id = 2
    tok.convert_tokens_to_ids = MagicMock(return_value=-1)
    tok.apply_chat_template = MagicMock(
        return_value={"input_ids": torch.tensor([[1, 2, 3]], dtype=torch.long)},
    )
    tok.side_effect = AssertionError("tokenizer() should not run in chat-template path")

    model = MagicMock()
    model.device = torch.device("cpu")
    model.generate = MagicMock()

    out = _generate_with_loaded_causal_lm(
        model,
        tok,
        "dummy-model",
        "Hello pipeline",
        max_new_tokens=8,
        inference_settings=None,
    )
    assert out == ""
    tok.apply_chat_template.assert_called_once()
    args, _kwargs = tok.apply_chat_template.call_args
    assert args[0] == [{"role": "user", "content": "Hello pipeline"}]


@pytest.mark.usefixtures("monkeypatch")
def test_pipeline_force_alpaca_skips_chat_template(monkeypatch) -> None:
    import src.content.brain as brain

    monkeypatch.setenv("AQUADUCT_PIPELINE_FORCE_ALPACA", "1")
    monkeypatch.setattr(brain, "_llm_max_input_tokens_cap", lambda *_a, **_k: 8192)
    monkeypatch.setattr(brain, "cuda_device_reported_by_torch", lambda: False)
    monkeypatch.setattr(brain, "dprint", lambda *a, **k: None)

    class _FakeStreamer:
        def __init__(self, *a, **k) -> None:
            pass

        def __iter__(self):
            return iter(())

    monkeypatch.setattr(
        "src.models.hf_transformers_imports.text_iterator_streamer_cls",
        lambda: _FakeStreamer,
    )

    class _Inp(dict):
        """HF BatchEncoding stand-in: mapping + ``.to()`` for device move."""

        def __init__(self) -> None:
            super().__init__(input_ids=torch.tensor([[9, 9]], dtype=torch.long))

        def to(self, _d) -> _Inp:
            return self

    tok = MagicMock()
    tok.return_value = _Inp()
    tok.chat_template = "{% mock %}"
    tok.eos_token_id = 2
    tok.convert_tokens_to_ids = MagicMock(return_value=-1)
    tok.apply_chat_template = MagicMock(side_effect=AssertionError("apply_chat_template must not run when forced"))

    model = MagicMock()
    model.device = torch.device("cpu")
    model.generate = MagicMock()

    _generate_with_loaded_causal_lm(
        model,
        tok,
        "dummy-model",
        "Hi",
        max_new_tokens=4,
        inference_settings=None,
    )
    assert tok.apply_chat_template.call_count == 0
    assert tok.call_count == 1


@pytest.mark.usefixtures("monkeypatch")
def test_pipeline_plain_prompt_when_no_chat_template(monkeypatch) -> None:
    import src.content.brain as brain

    monkeypatch.delenv("AQUADUCT_PIPELINE_FORCE_ALPACA", raising=False)
    monkeypatch.setattr(brain, "_llm_max_input_tokens_cap", lambda *_a, **_k: 8192)
    monkeypatch.setattr(brain, "cuda_device_reported_by_torch", lambda: False)
    monkeypatch.setattr(brain, "dprint", lambda *a, **k: None)

    class _FakeStreamer:
        def __init__(self, *a, **k) -> None:
            pass

        def __iter__(self):
            return iter(())

    monkeypatch.setattr(
        "src.models.hf_transformers_imports.text_iterator_streamer_cls",
        lambda: _FakeStreamer,
    )

    class _Inp(dict):
        """HF BatchEncoding stand-in: mapping + ``.to()`` for device move."""

        def __init__(self) -> None:
            super().__init__(input_ids=torch.tensor([[9, 9]], dtype=torch.long))

        def to(self, _d) -> _Inp:
            return self

    tok = MagicMock()
    tok.return_value = _Inp()
    tok.chat_template = None
    tok.eos_token_id = 2
    tok.convert_tokens_to_ids = MagicMock(return_value=-1)
    tok.apply_chat_template = MagicMock(side_effect=AssertionError("no chat template"))

    model = MagicMock()
    model.device = torch.device("cpu")
    model.generate = MagicMock()

    _generate_with_loaded_causal_lm(
        model,
        tok,
        "dummy-model",
        "Hi",
        max_new_tokens=4,
        inference_settings=None,
    )
    assert tok.call_count == 1
    full = tok.call_args[0][0]
    assert full.startswith("### Instruction:\nHi")
    assert "### Response:\n" in full


@pytest.mark.usefixtures("monkeypatch")
def test_pipeline_chat_template_strips_wrapped_alpaca_prompt(monkeypatch) -> None:
    import src.content.brain as brain

    monkeypatch.delenv("AQUADUCT_PIPELINE_FORCE_ALPACA", raising=False)
    monkeypatch.setattr(brain, "_llm_max_input_tokens_cap", lambda *_a, **_k: 8192)
    monkeypatch.setattr(brain, "cuda_device_reported_by_torch", lambda: False)
    monkeypatch.setattr(brain, "dprint", lambda *a, **k: None)

    class _FakeStreamer:
        def __init__(self, *a, **k) -> None:
            pass

        def __iter__(self):
            return iter(())

    monkeypatch.setattr(
        "src.models.hf_transformers_imports.text_iterator_streamer_cls",
        lambda: _FakeStreamer,
    )

    tok = MagicMock()
    tok.chat_template = "{% mock %}"
    tok.eos_token_id = 2
    tok.convert_tokens_to_ids = MagicMock(return_value=-1)
    tok.apply_chat_template = MagicMock(
        return_value={"input_ids": torch.tensor([[1, 2, 3]], dtype=torch.long)},
    )
    tok.side_effect = AssertionError("tokenizer() should not run")

    model = MagicMock()
    model.device = torch.device("cpu")
    model.generate = MagicMock()

    wrapped = "### Instruction:\nOnly this line.\n\n### Response:\n"
    _generate_with_loaded_causal_lm(
        model,
        tok,
        "dummy-model",
        wrapped,
        max_new_tokens=8,
        inference_settings=None,
    )
    args, _kwargs = tok.apply_chat_template.call_args
    assert args[0] == [{"role": "user", "content": "Only this line."}]
