"""
Mocked loader tests for ``load_causal_lm_from_pretrained`` quant chain.

We monkeypatch ``causal_lm_stack`` and ``src.util.cuda_capabilities.torch_cuda_kernels_work``
to verify which BitsAndBytesConfig (if any) is requested for each quant mode without
importing ``transformers``/``bitsandbytes`` runtimes.
"""
from __future__ import annotations

import types
from typing import Any

import pytest


class _FakeBnB:
    """Stand-in for transformers.BitsAndBytesConfig that records its kwargs."""

    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        type(self).last_kwargs = dict(kwargs)


class _FakeAutoModel:
    """Records ``from_pretrained`` calls and returns a dummy model."""

    calls: list[dict[str, Any]] = []

    @classmethod
    def from_pretrained(cls, load_path: str, **kwargs: Any) -> object:
        cls.calls.append({"load_path": load_path, **kwargs})
        return types.SimpleNamespace(device="cuda:0")


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    _FakeAutoModel.calls.clear()
    _FakeBnB.last_kwargs = {}


def _patch_brain(monkeypatch: pytest.MonkeyPatch, *, cuda_ok: bool = True) -> None:
    monkeypatch.setattr(
        "src.models.hf_transformers_imports.causal_lm_stack",
        lambda: (_FakeAutoModel, object(), _FakeBnB),
    )
    monkeypatch.setattr("src.models.torch_dtypes.torch_float16", lambda: "fp16-marker")
    import src.util.cuda_capabilities as cc

    monkeypatch.setattr(cc, "torch_cuda_kernels_work", lambda: cuda_ok)


def test_loader_quant_mode_nf4_4bit_invokes_bnb_4bit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_brain(monkeypatch, cuda_ok=True)
    from src.content.brain import load_causal_lm_from_pretrained

    load_causal_lm_from_pretrained("/tmp/fake-model", quant_mode="nf4_4bit", cuda_device_index=0)

    # First call should include a BitsAndBytesConfig configured for 4-bit.
    assert _FakeAutoModel.calls, "from_pretrained was never called"
    bnb = _FakeAutoModel.calls[0].get("quantization_config")
    assert isinstance(bnb, _FakeBnB)
    assert bnb.kwargs.get("load_in_4bit") is True


def test_loader_quant_mode_int8_invokes_bnb_8bit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_brain(monkeypatch, cuda_ok=True)
    from src.content.brain import load_causal_lm_from_pretrained

    load_causal_lm_from_pretrained("/tmp/fake-model", quant_mode="int8", cuda_device_index=0)

    bnb = _FakeAutoModel.calls[0].get("quantization_config")
    assert isinstance(bnb, _FakeBnB)
    assert bnb.kwargs.get("load_in_8bit") is True


def test_loader_quant_mode_fp16_skips_bnb(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_brain(monkeypatch, cuda_ok=True)
    from src.content.brain import load_causal_lm_from_pretrained

    load_causal_lm_from_pretrained("/tmp/fake-model", quant_mode="fp16", cuda_device_index=0)

    assert _FakeAutoModel.calls
    assert _FakeAutoModel.calls[0].get("quantization_config") is None


def test_loader_legacy_try_4bit_true_uses_4bit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_brain(monkeypatch, cuda_ok=True)
    from src.content.brain import load_causal_lm_from_pretrained

    # No explicit quant_mode; legacy try_4bit=True should still pick NF4 4-bit.
    load_causal_lm_from_pretrained("/tmp/fake-model", try_4bit=True, cuda_device_index=0)

    bnb = _FakeAutoModel.calls[0].get("quantization_config")
    assert isinstance(bnb, _FakeBnB)
    assert bnb.kwargs.get("load_in_4bit") is True


def test_loader_no_cuda_loads_on_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_brain(monkeypatch, cuda_ok=False)
    import src.util.cuda_capabilities as cc

    monkeypatch.setattr(cc, "cuda_device_reported_by_torch", lambda: False)
    monkeypatch.setattr(
        "src.models.torch_install.pytorch_cpu_wheel_with_nvidia_gpu_present",
        lambda: False,
    )
    from src.content.brain import load_causal_lm_from_pretrained

    load_causal_lm_from_pretrained("/tmp/fake-model", quant_mode="nf4_4bit")
    # When CUDA is not usable we never request BnB; we go straight to CPU.
    assert _FakeAutoModel.calls
    call = _FakeAutoModel.calls[0]
    assert call.get("device_map") == "cpu"
    assert call.get("quantization_config") is None
