from __future__ import annotations

from src.content.llm_chat_system_prompt import build_system_prompt


def test_slim_prompt_includes_tabs_and_tutorials() -> None:
    p = build_system_prompt()
    assert "Run" in p
    assert "Model" in p
    assert "welcome" in p
    assert "tasks_library" in p


def test_slim_prompt_has_anti_code_dump_rule() -> None:
    p = build_system_prompt()
    assert "Modified Code" in p or "code blocks" in p
    assert "Documentation excerpts" in p


def test_slim_prompt_reasonable_size() -> None:
    p = build_system_prompt()
    assert len(p) < 8000
