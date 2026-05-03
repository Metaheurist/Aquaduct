"""Budget tests for LLM chat composer limits."""

from __future__ import annotations

from src.core.config import AppSettings
from src.util import llm_chat_budget as lb


def test_local_budget_uses_script_profile(monkeypatch) -> None:
    monkeypatch.setenv("AQUADUCT_LLM_MAX_INPUT_TOKENS", "")
    monkeypatch.setattr(
        lb,
        "local_llm_chat_context_tokens",
        lambda _k, _s: 2048,
    )
    settings = AppSettings()
    cap, ctx = lb.composer_char_limit(
        mode="local",
        model_key="Qwen/Qwen3-14B",
        settings=settings,
        system_prompt="x" * 700,
        messages=[],
        max_history_messages=12,
    )
    assert ctx == 2048
    assert cap >= lb.MIN_MESSAGE_CHARS
    assert cap < lb.MAX_MESSAGE_CHARS_CAP


def test_env_override_tokens(monkeypatch) -> None:
    monkeypatch.setenv("AQUADUCT_LLM_MAX_INPUT_TOKENS", "4096")
    settings = AppSettings()
    assert lb.local_llm_chat_context_tokens("meta-llama/Llama-3.1-8B-Instruct", settings) == 4096


def test_api_budget_openai_groq() -> None:
    assert lb.api_llm_chat_context_tokens("openai", "gpt-4o-mini") == 128_000
    assert lb.api_llm_chat_context_tokens("groq", "llama-3.1-8b-instant") == 8192
    assert lb.api_llm_chat_context_tokens("groq", "llama-3.3-70b-versatile") == 32_768


def test_trim_messages_keeps_newest() -> None:
    sys = "system" * 20
    msgs = [{"role": "user", "content": "old " * 400}, {"role": "assistant", "content": "a" * 400}]
    msgs.append({"role": "user", "content": "newest"})
    out = lb.trim_messages_to_budget(
        msgs,
        system_prompt=sys,
        context_tokens=256,
        max_new_tokens=64,
        reserve=32,
        format_overhead_tokens=24,
    )
    assert out[-1]["content"] == "newest"
    assert all(m.get("role") != "system" for m in out)


def test_effective_max_new_tokens_api() -> None:
    settings = AppSettings()
    assert lb.effective_max_new_tokens_for_chat(mode="api", model_key="x", settings=settings, cap=256) <= 1024

