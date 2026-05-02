"""
Shared causal-LM tokenizer/model holder for sequential pipeline LLM steps.

Keeps one load across script expansion, generation, refinement, factcheck polish, and cast
when callers pass the same holder dict — avoids redundant multi-minute reloads.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def new_llm_holder() -> dict[str, Any]:
    """Create an empty holder. Keys: tokenizer, model, hub_model_id."""
    return {"tokenizer": None, "model": None, "hub_model_id": ""}


def dispose_llm_holder(holder: MutableMapping[str, Any] | None) -> None:
    """Release weights and clear holder fields."""
    if holder is None:
        return
    try:
        from src.content.brain import _dispose_causal_lm_pair

        mod = holder.get("model")
        tok = holder.get("tokenizer")
        if mod is not None:
            _dispose_causal_lm_pair(mod, tok)
    except Exception:
        pass
    try:
        holder["model"] = None
        holder["tokenizer"] = None
        holder["hub_model_id"] = ""
    except Exception:
        pass
