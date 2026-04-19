from __future__ import annotations

from src.settings.api_model_catalog import (
    default_models_for_provider,
    default_openai_compatible_base_url_for_llm,
    provider_by_id,
    providers_for_role,
    uses_openai_chat_protocol_for_llm,
)


def test_provider_by_id():
    assert provider_by_id("openai") is not None
    assert provider_by_id("OPENAI") is not None
    assert provider_by_id("") is None
    assert provider_by_id("nope") is None


def test_providers_for_role_llm():
    ids = [p.id for p in providers_for_role("llm")]
    assert "openai" in ids
    assert "groq" in ids
    assert "openrouter" in ids
    assert "replicate" not in ids


def test_providers_for_role_image_includes_replicate():
    ids = [p.id for p in providers_for_role("image")]
    assert "openai" in ids
    assert "replicate" in ids


def test_default_models_for_provider_openai_llm():
    m = default_models_for_provider("openai", "llm")
    assert "gpt-4o-mini" in m


def test_uses_openai_chat_protocol_for_llm():
    assert uses_openai_chat_protocol_for_llm("openai")
    assert uses_openai_chat_protocol_for_llm("groq")
    assert not uses_openai_chat_protocol_for_llm("replicate")


def test_default_openai_compatible_base_url_for_llm():
    assert "groq.com" in (default_openai_compatible_base_url_for_llm("groq") or "")
    assert default_openai_compatible_base_url_for_llm("openai") is None
