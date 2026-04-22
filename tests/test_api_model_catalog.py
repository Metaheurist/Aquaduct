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
    assert ids[0] == "google_ai_studio"
    assert "openai" in ids
    assert "groq" in ids
    assert "openrouter" in ids
    assert "replicate" not in ids


def test_providers_for_role_image_includes_replicate():
    ids = [p.id for p in providers_for_role("image")]
    assert ids[0] == "siliconflow"
    assert "openai" in ids
    assert "replicate" in ids


def test_default_models_for_provider_openai_llm():
    m = default_models_for_provider("openai", "llm")
    assert "gpt-4o-mini" in m


def test_uses_openai_chat_protocol_for_llm():
    assert uses_openai_chat_protocol_for_llm("openai")
    assert uses_openai_chat_protocol_for_llm("google_ai_studio")
    assert uses_openai_chat_protocol_for_llm("groq")
    assert not uses_openai_chat_protocol_for_llm("replicate")


def test_default_openai_compatible_base_url_for_llm():
    assert "groq.com" in (default_openai_compatible_base_url_for_llm("groq") or "")
    assert "generativelanguage.googleapis.com" in (default_openai_compatible_base_url_for_llm("google_ai_studio") or "")
    assert default_openai_compatible_base_url_for_llm("openai") is None


def test_providers_for_role_video_voice_order():
    vids = [p.id for p in providers_for_role("video")]
    assert vids[0] == "magic_hour"
    assert "replicate" in vids
    oids = [p.id for p in providers_for_role("voice")]
    assert oids[0] == "inworld"
    assert "openai" in oids
