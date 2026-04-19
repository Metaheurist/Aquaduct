"""Resolve ``torch.float16`` for HF/transformers; fail clearly if PyTorch is missing or wrong."""

from __future__ import annotations


def _torch_broken(torch) -> bool:
    return not (hasattr(torch, "float16") and hasattr(torch, "float32") and hasattr(torch, "Tensor"))


def torch_float16():
    """
    Normal installs: ``torch.float16``.

    If ``torch`` is a stub or the wrong package (no ``float16`` / ``Tensor``), we raise with
    install instructions ÔÇö local LLM and diffusers cannot run without a real PyTorch wheel.
    """
    import torch

    if _torch_broken(torch):
        raise RuntimeError(
            "PyTorch is not installed correctly: `import torch` does not expose real dtypes "
            "(often a missing install or the wrong package named `torch`). "
            "From the repo: run `python scripts/install_pytorch.py --with-rest` inside your venv, "
            "or use Model / Install dependencies in the UI."
        ) from None

    return torch.float16
