"""
Stable imports for Hugging Face Transformers + PyTorch.

``transformers`` 5.x registers many symbols lazily. If the package was first
imported before ``torch`` was available, ``from transformers import AutoModelForCausalLM``
can fail. Importing ``torch`` first and falling back to concrete submodules avoids that.
"""

from __future__ import annotations

from typing import Any


def causal_lm_stack() -> tuple[Any, Any, Any]:
    import torch  # noqa: F401

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError:
        from transformers.models.auto.modeling_auto import AutoModelForCausalLM
        from transformers.models.auto.tokenization_auto import AutoTokenizer
        from transformers.utils.quantization_config import BitsAndBytesConfig

    return AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def text_iterator_streamer_cls() -> Any:
    try:
        from transformers import TextIteratorStreamer
    except ImportError:
        from transformers.generation.streamers import TextIteratorStreamer

    return TextIteratorStreamer
