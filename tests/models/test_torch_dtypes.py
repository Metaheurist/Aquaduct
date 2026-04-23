from __future__ import annotations


def test_torch_float16_matches_torch_when_available() -> None:
    import torch

    if not hasattr(torch, "float16"):
        import pytest

        pytest.skip("torch.float16 missing (broken PyTorch install)")
    from src.models.torch_dtypes import torch_float16

    assert torch_float16() is torch.float16
