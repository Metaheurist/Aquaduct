from __future__ import annotations

from src.content.llm_session import dispose_llm_holder, new_llm_holder


def test_llm_holder_roundtrip_safe() -> None:
    h = new_llm_holder()
    dispose_llm_holder(h)
    assert h.get("model") is None
    dispose_llm_holder(None)
